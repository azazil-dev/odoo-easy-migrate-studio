# -*- coding: utf-8 -*-
from odoo import models, fields, api

class NiitsMigrateError(models.Model):
    _name = 'niits.migrate.error'
    _description = 'Migration Validation & Execution Error'
    _order = 'row_no, id'

    job_id = fields.Many2one('niits.migrate.job', string='Migration Job', required=True, ondelete='cascade', index=True)
    row_no = fields.Integer(string='Row Number', index=True)
    column = fields.Char(string='Column Name')
    value = fields.Char(string='Cell Value')
    message = fields.Text(string='Error Description / Suggestion', required=True)
    severity = fields.Selection([
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
    ], string='Severity', default='error', required=True)
