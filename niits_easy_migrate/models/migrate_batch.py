# -*- coding: utf-8 -*-
from odoo import models, fields, api

class NiitsMigrateBatch(models.Model):
    _name = 'niits.migrate.batch'
    _description = 'Migration Job Work Unit (Batch)'
    _order = 'sequence, id'

    job_id = fields.Many2one('niits.migrate.job', string='Migration Job', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='Batch Number', default=1)
    row_from = fields.Integer(string='Row From (1-indexed)')
    row_to = fields.Integer(string='Row To')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ], string='Status', default='pending', index=True, required=True)
    worker_pid = fields.Integer(string='Worker Process ID')
    heartbeat = fields.Datetime(string='Last Heartbeat')
    error_log = fields.Text(string='Execution Error')
