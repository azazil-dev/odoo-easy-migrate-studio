# -*- coding: utf-8 -*-
import datetime
import dateutil.parser
import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class BaseImportEngine:
    def __init__(self, env, job):
        self.env = env
        self.job = job
        self.type_rec = job.type_id
        self.target_model_name = job.type_id.model or job.custom_model_name
        self.target_model = env[self.target_model_name]
        self.mapping = job.mapping_id
        self.company = job.company_id
        self.ref_cache = {}  # (model, search_key, val): id

    def validate_batch(self, rows):
        raise NotImplementedError

    def execute_batch(self, rows):
        raise NotImplementedError


class OrmImportEngine(BaseImportEngine):
    """High-performance ORM-based import engine with pre-resolved references and batching."""

    def _get_context(self):
        ctx = dict(self.env.context)
        if self.job.engine_speed in ('balanced', 'fast'):
            ctx.update({
                'tracking_disable': True,
                'mail_create_nolog': True,
                'mail_notrack': True,
                'no_reset_password': True,
                'import_file': True,
                'recompute': False if self.job.engine_speed == 'fast' else True,
            })
        if self.company:
            ctx['allowed_company_ids'] = [self.company.id]
            ctx['company_id'] = self.company.id
        return ctx

    def _resolve_relation(self, target_model_name, search_key, raw_val):
        if not raw_val:
            return False
        cache_key = (target_model_name, search_key, str(raw_val).strip())
        if cache_key in self.ref_cache:
            return self.ref_cache[cache_key]

        val_str = str(raw_val).strip()
        rel_model = self.env[target_model_name]
        record_id = False

        if search_key == 'id':
            try:
                rec_id = int(val_str)
                if rel_model.browse(rec_id).exists():
                    record_id = rec_id
            except ValueError:
                pass
        elif search_key == 'xml_id':
            ref_rec = self.env.ref(val_str, raise_if_not_found=False)
            if ref_rec and ref_rec._name == target_model_name:
                record_id = ref_rec.id
        else:
            domain = [(search_key, '=', val_str)]
            if 'company_id' in rel_model._fields and self.company:
                domain = ['|', ('company_id', '=', False), ('company_id', '=', self.company.id)] + domain
            rec = rel_model.sudo().search(domain, limit=1)
            if rec:
                record_id = rec.id

        self.ref_cache[cache_key] = record_id
        return record_id

    def _convert_value(self, field_obj, raw_val, line_map):
        if raw_val is None or str(raw_val).strip() == '':
            if line_map.default_value:
                raw_val = line_map.default_value
            else:
                return False

        ftype = field_obj.type
        val_str = str(raw_val).strip()

        # Handle transformations
        if line_map.transform == 'upper':
            val_str = val_str.upper()
        elif line_map.transform == 'lower':
            val_str = val_str.lower()
        elif line_map.transform == 'title':
            val_str = val_str.title()
        elif line_map.transform == 'strip':
            val_str = val_str.strip()

        if ftype == 'boolean':
            return val_str.lower() in ('true', '1', 'yes', 'y', 't', 'true')
        elif ftype == 'integer':
            try:
                return int(float(val_str.replace(',', '')))
            except Exception:
                raise ValueError(_("Invalid integer: %s") % val_str)
        elif ftype == 'float' or ftype == 'monetary':
            try:
                return float(val_str.replace(',', ''))
            except Exception:
                raise ValueError(_("Invalid number: %s") % val_str)
        elif ftype == 'date':
            try:
                dt = dateutil.parser.parse(val_str)
                return dt.date().strftime('%Y-%m-%d')
            except Exception:
                raise ValueError(_("Invalid date: %s") % val_str)
        elif ftype == 'datetime':
            try:
                dt = dateutil.parser.parse(val_str)
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                raise ValueError(_("Invalid datetime: %s") % val_str)
        elif ftype == 'many2one':
            search_key = line_map.search_key or 'name'
            rel_id = self._resolve_relation(field_obj.comodel_name, search_key, val_str)
            if not rel_id:
                raise ValueError(_("Referenced %s not found with %s='%s'") % (field_obj.comodel_name, search_key, val_str))
            return rel_id
        elif ftype == 'selection':
            selection_keys = [s[0] for s in field_obj.selection] if isinstance(field_obj.selection, list) else []
            if val_str in selection_keys:
                return val_str
            # Try matching label
            if isinstance(field_obj.selection, list):
                for k, label in field_obj.selection:
                    if str(label).lower() == val_str.lower():
                        return k
            raise ValueError(_("Value '%s' is not in selection list for field %s") % (val_str, field_obj.name))
        else:
            return val_str

    def parse_row(self, row_dict):
        """Converts raw row dict into target field values according to mapping."""
        res = {}
        for line_map in self.mapping.line_ids:
            if not line_map.field_id:
                continue
            fname = line_map.field_id.name
            raw_val = row_dict.get(line_map.source_column, '')
            field_obj = self.target_model._fields.get(fname)
            if not field_obj:
                continue
            converted_val = self._convert_value(field_obj, raw_val, line_map)
            if converted_val is not False or field_obj.type == 'boolean':
                res[fname] = converted_val

        # Auto assign company if model has company_id
        if 'company_id' in self.target_model._fields and self.company and 'company_id' not in res:
            res['company_id'] = self.company.id

        # If partner customer/vendor rank
        if self.target_model._name == 'res.partner':
            if self.type_rec.code == 'customers' and 'customer_rank' not in res:
                res['customer_rank'] = 1
            elif self.type_rec.code == 'vendors' and 'supplier_rank' not in res:
                res['supplier_rank'] = 1

        return res

    def validate_batch(self, rows):
        """Dry-run validation for a batch of rows. Returns list of errors."""
        errors = []
        unique_key = self.job.type_id.unique_key or 'name'
        existing_keys = set()
        required_fields = [
            f.name for f, f_obj in self.target_model._fields.items()
            if getattr(f_obj, 'required', False) and not getattr(f_obj, 'compute', False) and f not in ('id', 'create_uid', 'create_date', 'write_uid', 'write_date')
        ]

        for row_no, row_dict in rows:
            try:
                parsed_vals = self.parse_row(row_dict)
                # Check required fields
                for req in required_fields:
                    if req not in parsed_vals or parsed_vals[req] is False or parsed_vals[req] is None or parsed_vals[req] == '':
                        errors.append({
                            'row_no': row_no,
                            'column': req,
                            'value': str(row_dict.get(req, '')),
                            'message': _("Required field '%s' is missing or empty") % req,
                            'severity': 'error',
                        })
                # Check unique key duplicates in batch
                if unique_key in parsed_vals:
                    ukey_val = parsed_vals[unique_key]
                    if ukey_val in existing_keys:
                        errors.append({
                            'row_no': row_no,
                            'column': unique_key,
                            'value': str(ukey_val),
                            'message': _("Duplicate unique key '%s' found within import file") % ukey_val,
                            'severity': 'warning' if self.job.mode == 'upsert' else 'error',
                        })
                    else:
                        existing_keys.add(ukey_val)

            except Exception as e:
                errors.append({
                    'row_no': row_no,
                    'column': 'ROW',
                    'value': str(row_dict)[:100],
                    'message': str(e),
                    'severity': 'error',
                })
        return errors

    def execute_batch(self, rows):
        """Processes and writes a batch of rows using ORM. Returns (success_count, failed_count, errors, undo_logs)."""
        ctx = self._get_context()
        env_ctx = self.env(context=ctx)
        target_model = env_ctx[self.target_model_name]
        unique_key = self.job.type_id.unique_key or 'name'
        mode = self.job.mode  # 'create', 'update', 'upsert'

        success_count = 0
        failed_count = 0
        errors = []
        undo_logs = []

        for row_no, row_dict in rows:
            try:
                parsed_vals = self.parse_row(row_dict)
                existing_rec = False
                if unique_key in parsed_vals and parsed_vals[unique_key]:
                    domain = [(unique_key, '=', parsed_vals[unique_key])]
                    if 'company_id' in target_model._fields and self.company:
                        domain = ['|', ('company_id', '=', False), ('company_id', '=', self.company.id)] + domain
                    existing_rec = target_model.search(domain, limit=1)

                if existing_rec:
                    if mode == 'create':
                        raise ValidationError(_("Record with %s='%s' already exists (Mode is Create Only)") % (unique_key, parsed_vals.get(unique_key)))
                    # Update or Upsert
                    old_vals = {}
                    for k in parsed_vals.keys():
                        val = getattr(existing_rec, k)
                        old_vals[k] = val.id if hasattr(val, 'id') else val
                    existing_rec.write(parsed_vals)
                    undo_logs.append({
                        'job_id': self.job.id,
                        'model': self.target_model_name,
                        'res_id': existing_rec.id,
                        'action': 'update',
                        'old_values': json.dumps(old_vals, default=str),
                    })
                    success_count += 1
                else:
                    if mode == 'update':
                        raise ValidationError(_("Record with %s='%s' not found for update (Mode is Update Only)") % (unique_key, parsed_vals.get(unique_key)))
                    # Create
                    new_rec = target_model.create(parsed_vals)
                    undo_logs.append({
                        'job_id': self.job.id,
                        'model': self.target_model_name,
                        'res_id': new_rec.id,
                        'action': 'create',
                        'old_values': '{}',
                    })
                    success_count += 1

            except Exception as e:
                failed_count += 1
                errors.append({
                    'job_id': self.job.id,
                    'row_no': row_no,
                    'column': 'ROW',
                    'value': str(row_dict)[:100],
                    'message': str(e),
                    'severity': 'error',
                })
                if self.job.error_policy == 'stop_first':
                    break

        return success_count, failed_count, errors, undo_logs
