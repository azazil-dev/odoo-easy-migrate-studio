# -*- coding: utf-8 -*-
from odoo import models, fields, api

class NiitsMigrateUndoLog(models.Model):
    _name = 'niits.migrate.undo.log'
    _description = 'Migration Undo Tracking Log'
    _order = 'id desc'

    job_id = fields.Many2one('niits.migrate.job', string='Migration Job', required=True, ondelete='cascade', index=True)
    model = fields.Char(string='Target Model', required=True, index=True)
    res_id = fields.Integer(string='Record ID', required=True, index=True)
    action = fields.Selection([
        ('create', 'Created Record'),
        ('update', 'Updated Record'),
    ], string='Action Taken', required=True)
    old_values = fields.Text(string='Previous Values (JSON)', default='{}')
    is_reverted = fields.Boolean(string='Reverted', default=False)
