# -*- coding: utf-8 -*-
from odoo import models, fields, api

class NiitsMigrateMapping(models.Model):
    _name = 'niits.migrate.mapping'
    _description = 'Migration Column Mapping Preset'

    name = fields.Char(string='Preset Name', required=True)
    type_id = fields.Many2one('niits.migrate.type', string='Data Type', ondelete='cascade')
    model_id = fields.Many2one('ir.model', string='Model', ondelete='cascade')
    model_name = fields.Char(related='model_id.model', string='Target Model Name', readonly=True)
    line_ids = fields.One2many('niits.migrate.mapping.line', 'mapping_id', string='Mapping Lines')
    user_id = fields.Many2one('res.users', string='Owner', default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)


class NiitsMigrateMappingLine(models.Model):
    _name = 'niits.migrate.mapping.line'
    _description = 'Migration Column Mapping Line'
    _order = 'sequence, id'

    mapping_id = fields.Many2one('niits.migrate.mapping', string='Mapping Header', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    source_column = fields.Char(string='Source Column (File Header)', required=True)
    field_id = fields.Many2one('ir.model.fields', string='Target Odoo Field', ondelete='cascade')
    field_type = fields.Selection(related='field_id.ttype', string='Field Type', readonly=True)
    search_key = fields.Selection([
        ('name', 'Name / Display Name'),
        ('code', 'Code / Internal Ref'),
        ('default_code', 'Default Code / Internal Reference'),
        ('barcode', 'Barcode'),
        ('email', 'Email Address'),
        ('id', 'Database ID'),
        ('xml_id', 'External ID (XML ID)'),
    ], string='Relational Lookup Key', default='name')
    transform = fields.Selection([
        ('none', 'None'),
        ('strip', 'Trim Whitespace'),
        ('upper', 'Uppercase'),
        ('lower', 'Lowercase'),
        ('title', 'Title Case'),
    ], string='Transformation', default='strip')
    default_value = fields.Char(string='Default Value (if empty)')
    is_required = fields.Boolean(related='field_id.required', string='Required')
