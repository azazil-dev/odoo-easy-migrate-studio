import base64
import difflib
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..services.source_adapter import FileAdapter

class NiitsMigrateStudioWizard(models.TransientModel):
    _name = 'niits.migrate.studio.wizard'
    _description = 'Interactive 4-Step Migration Studio Wizard'

    step = fields.Selection([
        ('step1', 'Step 1: Source & File'),
        ('step2', 'Step 2: Smart Column Mapping'),
        ('step3', 'Step 3: Engine & Options'),
        ('step4', 'Step 4: Review & Run'),
    ], string='Current Step', default='step1', required=True)

    # Step 1 Fields
    type_id = fields.Many2one('niits.migrate.type', string='Select Data Type', required=True)
    is_generic = fields.Boolean(string='Generic Model Mode', default=False)
    custom_model_id = fields.Many2one('ir.model', string='Select Target Model')
    file_data = fields.Binary(string='Upload CSV or Excel File', required=False)
    filename = fields.Char(string='Filename')

    # Step 2 Fields: Mapping
    mapping_id = fields.Many2one('niits.migrate.mapping', string='Use Existing Preset')
    save_as_preset = fields.Boolean(string='Save this Mapping as Preset', default=False)
    preset_name = fields.Char(string='Preset Name')
    mapping_line_ids = fields.One2many('niits.migrate.studio.wizard.mapping.line', 'wizard_id', string='Column Mappings')
    preview_html = fields.Html(string='First 20 Rows Preview', readonly=True)

    # Step 3 Fields: Options
    mode = fields.Selection([
        ('create', 'Create Only (Skip Existing)'),
        ('update', 'Update Only (Error if Not Found)'),
        ('upsert', 'Create or Update (Upsert by Unique Key)'),
    ], string='Import Mode', default='upsert', required=True)

    engine_speed = fields.Selection([
        ('safe', 'Safe Mode (Full Tracking & Constraints)'),
        ('balanced', 'Balanced (Optimized ORM)'),
        ('fast', 'Fast Mode (Lightning Batch ORM)'),
    ], string='Engine Speed', default='fast', required=True)

    workers = fields.Integer(string='Worker Processes', default=2)
    batch_size = fields.Integer(string='Batch Size', default=500)
    error_policy = fields.Selection([
        ('skip', 'Skip Erroneous Rows'),
        ('stop_first', 'Stop at First Error'),
        ('all_or_none', 'All or Nothing (Strict Rollback)'),
    ], string='Error Handling Policy', default='skip', required=True)
    company_id = fields.Many2one('res.company', string='Target Company', default=lambda self: self.env.company, required=True)

    # Step 4: Job Reference
    job_id = fields.Many2one('niits.migrate.job', string='Created Job', readonly=True)

    @api.onchange('type_id')
    def _onchange_type_id(self):
        if self.type_id and self.type_id.code == 'generic':
            self.is_generic = True
        else:
            self.is_generic = False

    def action_download_template(self):
        self.ensure_one()
        if not self.type_id:
            raise UserError(_("Please select a data type first."))
        if self.type_id.template_data:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content?model=niits.migrate.type&id={self.type_id.id}&field=template_data&filename={self.type_id.template_filename or "template.csv"}&download=true',
                'target': 'self',
            }
        else:
            raise UserError(_("No sample template configured for this type yet."))

    def action_step1_next(self):
        """Move from Step 1 to Step 2: Parse headers and build smart column mapping."""
        self.ensure_one()
        if not self.file_data:
            raise UserError(_("Please upload a CSV or XLSX data file."))

        raw_data = base64.b64decode(self.file_data)
        adapter = FileAdapter()
        headers = adapter.read_headers(raw_data, filename=self.filename)
        if not headers:
            raise UserError(_("No header columns could be found in the uploaded file."))

        # Determine target model
        target_model_name = self.custom_model_id.model if (self.is_generic and self.custom_model_id) else self.type_id.model
        if not target_model_name or target_model_name not in self.env:
            raise UserError(_("Target model '%s' is not installed or invalid.") % target_model_name)

        target_model = self.env[target_model_name]
        all_fields = self.env['ir.model.fields'].search([('model', '=', target_model_name)])
        field_dict = {f.name: f for f in all_fields}
        field_labels = {f.field_description.lower(): f for f in all_fields if f.field_description}

        # Clear existing lines
        self.mapping_line_ids.unlink()

        mapping_lines = []
        seq = 10
        for col in headers:
            col_clean = col.strip()
            matched_field = None

            # 1. Exact field name match
            if col_clean.lower() in field_dict:
                matched_field = field_dict[col_clean.lower()]
            # 2. Exact label match
            elif col_clean.lower() in field_labels:
                matched_field = field_labels[col_clean.lower()]
            # 3. Fuzzy match against field descriptions
            else:
                best_matches = difflib.get_close_matches(col_clean.lower(), list(field_labels.keys()), n=1, cutoff=0.75)
                if best_matches:
                    matched_field = field_labels[best_matches[0]]
                else:
                    best_tech = difflib.get_close_matches(col_clean.lower(), list(field_dict.keys()), n=1, cutoff=0.75)
                    if best_tech:
                        matched_field = field_dict[best_tech[0]]

            mapping_lines.append((0, 0, {
                'sequence': seq,
                'source_column': col_clean,
                'field_id': matched_field.id if matched_field else False,
                'search_key': 'name' if matched_field and matched_field.ttype == 'many2one' else False,
                'transform': 'strip',
            }))
            seq += 10

        # Build preview HTML table of first 20 rows
        preview_rows = adapter.read_rows(raw_data, filename=self.filename, limit=20)
        table_html = "<div class='table-responsive'><table class='table table-sm table-striped table-bordered'>"
        table_html += "<thead><tr>" + "".join([f"<th>{h}</th>" for h in headers]) + "</tr></thead><tbody>"
        for row_idx, rdict in preview_rows:
            table_html += "<tr>" + "".join([f"<td>{rdict.get(h, '')}</td>" for h in headers]) + "</tr>"
        table_html += "</tbody></table></div>"

        self.write({
            'step': 'step2',
            'mapping_line_ids': mapping_lines,
            'preview_html': table_html,
        })
        return self._reopen_wizard()

    def action_step2_back(self):
        self.write({'step': 'step1'})
        return self._reopen_wizard()

    def action_step2_next(self):
        self.ensure_one()
        mapped_count = len(self.mapping_line_ids.filtered(lambda l: bool(l.field_id)))
        if mapped_count == 0:
            raise UserError(_("Please map at least one column to a target Odoo field."))
        self.write({'step': 'step3'})
        return self._reopen_wizard()

    def action_step3_back(self):
        self.write({'step': 'step2'})
        return self._reopen_wizard()

    def action_step3_next(self):
        """Creates Job record, Mapping record, and executes validation."""
        self.ensure_one()
        # Save or Create Mapping preset
        mapping_vals = {
            'name': self.preset_name or _("Mapping for %s - %s") % (self.type_id.name, fields.Date.today()),
            'type_id': self.type_id.id,
            'model_id': self.env['ir.model'].search([('model', '=', self.type_id.model or self.custom_model_id.model)], limit=1).id,
            'line_ids': [(0, 0, {
                'sequence': l.sequence,
                'source_column': l.source_column,
                'field_id': l.field_id.id,
                'search_key': l.search_key or 'name',
                'transform': l.transform or 'strip',
                'default_value': l.default_value,
            }) for l in self.mapping_line_ids if l.field_id]
        }
        mapping_rec = self.env['niits.migrate.mapping'].create(mapping_vals)

        # Create Attachment
        att = self.env['ir.attachment'].create({
            'name': self.filename or 'import_data.csv',
            'datas': self.file_data,
            'res_model': 'niits.migrate.job',
        })

        # Create Job
        job = self.env['niits.migrate.job'].create({
            'name': _("Import: %s (%s)") % (self.type_id.name, self.filename or 'file'),
            'type_id': self.type_id.id,
            'custom_model_name': self.custom_model_id.model if self.custom_model_id else False,
            'source_attachment_id': att.id,
            'source_filename': self.filename,
            'mapping_id': mapping_rec.id,
            'mode': self.mode,
            'engine_speed': self.engine_speed,
            'workers': self.workers,
            'batch_size': self.batch_size,
            'error_policy': self.error_policy,
            'company_id': self.company_id.id,
        })
        att.write({'res_id': job.id})

        # Validate job immediately
        job.action_validate_job()

        self.write({
            'step': 'step4',
            'job_id': job.id,
            'mapping_id': mapping_rec.id,
        })
        return self._reopen_wizard()

    def action_step4_back(self):
        self.write({'step': 'step3'})
        return self._reopen_wizard()

    def action_run_job(self):
        self.ensure_one()
        if not self.job_id:
            raise UserError(_("No job initialized."))
        self.job_id.action_start_job()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Migration Job"),
            'res_model': 'niits.migrate.job',
            'res_id': self.job_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _reopen_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }


class NiitsMigrateStudioWizardMappingLine(models.TransientModel):
    _name = 'niits.migrate.studio.wizard.mapping.line'
    _description = 'Wizard Mapping Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('niits.migrate.studio.wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Seq', default=10)
    source_column = fields.Char(string='Source Column', required=True)
    field_id = fields.Many2one('ir.model.fields', string='Target Field')
    field_type = fields.Selection(related='field_id.ttype', string='Type', readonly=True)
    search_key = fields.Selection([
        ('name', 'Name'),
        ('code', 'Code / Ref'),
        ('default_code', 'Default Code'),
        ('barcode', 'Barcode'),
        ('email', 'Email'),
        ('id', 'Database ID'),
        ('xml_id', 'XML ID'),
    ], string='Lookup Key', default='name')
    transform = fields.Selection([
        ('none', 'None'),
        ('strip', 'Trim'),
        ('upper', 'Uppercase'),
        ('lower', 'Lowercase'),
        ('title', 'Title Case'),
    ], string='Transform', default='strip')
    default_value = fields.Char(string='Default Value')
