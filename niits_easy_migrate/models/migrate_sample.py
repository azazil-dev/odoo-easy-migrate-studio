# -*- coding: utf-8 -*-
from odoo import models, fields, api

class NiitsMigrateSample(models.Model):
    _name = 'niits.migrate.sample'
    _description = 'Migration Sample Pack'
    _order = 'sequence, id'

    name = fields.Char(string='Sample Name', required=True)
    sequence = fields.Integer(string='Import Order Sequence', default=10)
    type_id = fields.Many2one('niits.migrate.type', string='Data Type', required=True, ondelete='cascade')
    file_name = fields.Char(string='File Name', required=True)
    file_data = fields.Binary(string='File Content', attachment=True, required=True)
    description = fields.Text(string='Sample Notes')
