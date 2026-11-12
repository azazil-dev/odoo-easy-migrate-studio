# -*- coding: utf-8 -*-
import base64
import json
import logging
import os
import time
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from ..services.source_adapter import FileAdapter
from ..services.import_engine import OrmImportEngine

_logger = logging.getLogger(__name__)

class NiitsMigrateJob(models.Model):
    _name = 'niits.migrate.job'
    _description = 'Migration Job Session'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Job Name / Ref', required=True, default=lambda self: _('New Import Job'), tracking=True)
    type_id = fields.Many2one('niits.migrate.type', string='Data Type', tracking=True)
    custom_model_name = fields.Char(string='Custom Model Name (Generic Mode)', tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('validating', 'Validating'),
        ('ready', 'Ready to Run'),
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('done', 'Completed'),
        ('failed', 'Failed'),
        ('undone', 'Undone / Reverted'),
    ], string='Status', default='draft', required=True, tracking=True, index=True)

    source_attachment_id = fields.Many2one('ir.attachment', string='Source File Attachment', ondelete='set null')
    source_filename = fields.Char(string='Source Filename')
    mapping_id = fields.Many2one('niits.migrate.mapping', string='Mapping Preset', ondelete='set null')

    mode = fields.Selection([
        ('create', 'Create Only'),
        ('update', 'Update Only'),
        ('upsert', 'Create or Update (Upsert)'),
    ], string='Import Mode', default='upsert', required=True)

    engine_speed = fields.Selection([
        ('safe', 'Safe (Full Validation & Tracking)'),
        ('balanced', 'Balanced (Optimized ORM)'),
        ('fast', 'Fast (Lightning Batch ORM)'),
    ], string='Engine Speed', default='fast', required=True)

    workers = fields.Integer(string='Workers Count', default=2)
    batch_size = fields.Integer(string='Batch Size', default=500)
    error_policy = fields.Selection([
        ('skip', 'Skip Erroneous Rows'),
        ('stop_first', 'Stop at First Error'),
        ('all_or_none', 'All or Nothing (Strict)'),
    ], string='Error Handling Policy', default='skip', required=True)

    company_id = fields.Many2one('res.company', string='Target Company', default=lambda self: self.env.company, required=True)
    user_id = fields.Many2one('res.users', string='Started By', default=lambda self: self.env.user, required=True)

    total_rows = fields.Integer(string='Total Rows', default=0)
    done_rows = fields.Integer(string='Processed Rows', default=0)
    failed_rows = fields.Integer(string='Failed Rows', default=0)
    skipped_rows = fields.Integer(string='Skipped Rows', default=0)
    progress_percentage = fields.Float(string='Progress (%)', compute='_compute_progress', store=False)
    rows_per_second = fields.Float(string='Rows / Sec', default=0.0)

    started_at = fields.Datetime(string='Started At')
    finished_at = fields.Datetime(string='Finished At')
    duration_str = fields.Char(string='Duration', compute='_compute_duration', store=False)

    batch_ids = fields.One2many('niits.migrate.batch', 'job_id', string='Batches')
    error_ids = fields.One2many('niits.migrate.error', 'job_id', string='Error Log')
    undo_log_ids = fields.One2many('niits.migrate.undo.log', 'job_id', string='Undo History')

    @api.depends('total_rows', 'done_rows')
    def _compute_progress(self):
        for rec in self:
            if rec.total_rows > 0:
                rec.progress_percentage = round((rec.done_rows / rec.total_rows) * 100.0, 1)
            elif rec.state == 'done':
                rec.progress_percentage = 100.0
            else:
                rec.progress_percentage = 0.0

    @api.depends('started_at', 'finished_at')
    def _compute_duration(self):
        for rec in self:
            if rec.started_at and rec.finished_at:
                diff = (rec.finished_at - rec.started_at).total_seconds()
                mins, secs = divmod(diff, 60)
                rec.duration_str = f"{int(mins)}m {int(secs)}s"
            elif rec.started_at:
                diff = (fields.Datetime.now() - rec.started_at).total_seconds()
                mins, secs = divmod(diff, 60)
                rec.duration_str = f"{int(mins)}m {int(secs)}s"
            else:
                rec.duration_str = "-"

    def _get_source_raw_data(self):
        self.ensure_one()
        if not self.source_attachment_id:
            return b''
        if getattr(self.source_attachment_id, 'raw', False):
            return self.source_attachment_id.raw
        if self.source_attachment_id.datas:
            return base64.b64decode(self.source_attachment_id.datas)
        return b''

    def action_validate_job(self):
        """Runs pre-import dry-run validation without writing to DB."""
        self.ensure_one()
        if not self.source_attachment_id or (not getattr(self.source_attachment_id, 'raw', False) and not self.source_attachment_id.datas):
            raise UserError(_("No source data file attached to this job."))
        if not self.mapping_id:
            raise UserError(_("No mapping configuration set."))

        self.write({'state': 'validating'})
        self.error_ids.unlink()

        raw_data = self._get_source_raw_data()
        adapter = FileAdapter()
        engine = OrmImportEngine(self.env, self)

        all_rows = adapter.read_rows(raw_data, filename=self.source_filename)
        self.total_rows = len(all_rows)

        errors = engine.validate_batch(all_rows)
        if errors:
            err_records = []
            for err in errors:
                err_records.append((0, 0, {
                    'row_no': err.get('row_no', 0),
                    'column': err.get('column', ''),
                    'value': err.get('value', ''),
                    'message': err.get('message', ''),
                    'severity': err.get('severity', 'error'),
                }))
            self.write({
                'error_ids': err_records,
                'state': 'ready' if self.error_policy == 'skip' else 'draft'
            })
            if self.error_policy != 'skip':
                self.message_post(body=_("Validation completed with %d error(s). Please review and correct.") % len(errors))
                return False
        else:
            self.write({'state': 'ready'})

        self.message_post(body=_("Validation passed successfully! Ready to run import."))
        return True

    def action_start_job(self):
        """Prepares batches and triggers immediate or background execution."""
        self.ensure_one()
        if not self.source_attachment_id or (not getattr(self.source_attachment_id, 'raw', False) and not self.source_attachment_id.datas):
            raise UserError(_("No source data file attached."))
        if not self.mapping_id:
            raise UserError(_("No mapping configuration set."))

        raw_data = self._get_source_raw_data()
        adapter = FileAdapter()
        total = adapter.get_total_rows(raw_data, filename=self.source_filename)
        self.total_rows = total

        # Split into batches
        self.batch_ids.unlink()
        batch_size = max(10, self.batch_size or 500)
        batch_vals = []
        seq = 1
        for offset in range(0, total, batch_size):
            batch_vals.append((0, 0, {
                'sequence': seq,
                'row_from': offset + 1,
                'row_to': min(offset + batch_size, total),
                'state': 'pending',
            }))
            seq += 1

        self.write({
            'batch_ids': batch_vals,
            'state': 'running',
            'started_at': fields.Datetime.now(),
            'done_rows': 0,
            'failed_rows': 0,
            'skipped_rows': 0,
        })
        self.message_post(body=_("Migration job started with %d batches.") % len(batch_vals))

        # Process first batches synchronously or via cron
        self.process_next_batch()

    def process_next_batch(self):
        """Processes the next pending batch for this job."""
        self.ensure_one()
        if self.state != 'running':
            return False

        batch = self.batch_ids.filtered(lambda b: b.state == 'pending')[:1]
        if not batch:
            # Check if all batches are finished
            all_done = all(b.state in ('done', 'failed') for b in self.batch_ids)
            if all_done:
                has_failed = any(b.state == 'failed' for b in self.batch_ids)
                self.write({
                    'state': 'failed' if has_failed and self.error_policy == 'all_or_none' else 'done',
                    'finished_at': fields.Datetime.now(),
                })
                self.message_post(body=_("Migration job finished! Total rows processed: %d") % self.done_rows)
            return False

        batch.write({
            'state': 'running',
            'worker_pid': os.getpid(),
            'heartbeat': fields.Datetime.now(),
        })

        raw_data = self._get_source_raw_data()
        adapter = FileAdapter()
        limit = batch.row_to - batch.row_from + 1
        offset = batch.row_from - 1

        rows = adapter.read_rows(raw_data, filename=self.source_filename, limit=limit, offset=offset)
        engine = OrmImportEngine(self.env, self)

        t_start = time.time()
        success, failed, errs, undos = engine.execute_batch(rows)
        t_elapsed = max(0.001, time.time() - t_start)

        # Log undo and errors
        if undos:
            self.env['niits.migrate.undo.log'].create(undos)
        if errs:
            self.env['niits.migrate.error'].create(errs)

        batch.write({
            'state': 'done' if failed == 0 or self.error_policy == 'skip' else 'failed',
            'heartbeat': fields.Datetime.now(),
            'error_log': "\n".join([e.get('message', '') for e in errs]) if errs else False,
        })

        new_done = self.done_rows + success
        new_failed = self.failed_rows + failed
        rows_sec = round(len(rows) / t_elapsed, 1)

        self.write({
            'done_rows': new_done,
            'failed_rows': new_failed,
            'rows_per_second': rows_sec,
        })

        # Continue next batch if synchronous loop
        return True

    @api.model
    def run_cron_worker(self):
        """Cron entry point to process batches across active running jobs."""
        running_jobs = self.search([('state', '=', 'running')], limit=5)
        for job in running_jobs:
            try:
                job.process_next_batch()
            except Exception as e:
                _logger.exception("Error executing migration job %s: %s", job.id, e)

    def action_pause(self):
        self.write({'state': 'paused'})
        self.message_post(body=_("Migration job paused."))

    def action_resume(self):
        self.write({'state': 'running'})
        self.message_post(body=_("Migration job resumed."))
        self.process_next_batch()

    def action_cancel(self):
        self.write({'state': 'failed'})
        self.message_post(body=_("Migration job cancelled by user."))

    def action_retry_failed(self):
        failed_batches = self.batch_ids.filtered(lambda b: b.state == 'failed')
        failed_batches.write({'state': 'pending'})
        self.write({'state': 'running'})
        self.process_next_batch()

    def action_undo(self):
        """Performs one-click rollback of all created and updated records."""
        self.ensure_one()
        if not self.undo_log_ids:
            raise UserError(_("No undo history available for this job."))

        undone_count = 0
        skipped_count = 0

        # Undo in reverse order
        for log in self.undo_log_ids.filtered(lambda l: not l.is_reverted).sorted(key=lambda l: l.id, reverse=True):
            model_name = log.model
            if model_name not in self.env:
                skipped_count += 1
                continue
            rec = self.env[model_name].browse(log.res_id)
            if not rec.exists():
                log.is_reverted = True
                continue

            try:
                if log.action == 'create':
                    # Unlink created record
                    rec.unlink()
                    log.is_reverted = True
                    undone_count += 1
                elif log.action == 'update':
                    # Restore previous values
                    if log.old_values:
                        old_dict = json.loads(log.old_values)
                        rec.write(old_dict)
                    log.is_reverted = True
                    undone_count += 1
            except Exception as e:
                _logger.warning("Undo failed for %s ID %s: %s", model_name, log.res_id, e)
                skipped_count += 1

        self.write({'state': 'undone'})
        self.message_post(body=_("One-click Undo executed: %d records reverted, %d skipped.") % (undone_count, skipped_count))

    def action_view_records(self):
        """Opens list/form view of records created/modified by this job."""
        self.ensure_one()
        model_name = self.type_id.model or self.custom_model_name
        res_ids = self.undo_log_ids.mapped('res_id')
        return {
            'name': _("Migrated Records: %s") % (self.type_id.name or model_name),
            'type': 'ir.actions.act_window',
            'res_model': model_name,
            'view_mode': 'list,form',
            'domain': [('id', 'in', res_ids)],
        }
