# -*- coding: utf-8 -*-
from odoo import models, fields, api

class NiitsMigrateType(models.Model):
    _name = 'niits.migrate.type'
    _description = 'Migration Data Type Definition'
    _order = 'sequence, id'

    name = fields.Char(string='Data Type Name', required=True, translate=True)
    code = fields.Char(string='Code', required=True, index=True)
    sequence = fields.Integer(string='Sequence / Order', default=10)
    category = fields.Selection([
        ('master', 'Master Data'),
        ('inventory', 'Inventory & Stock'),
        ('accounting', 'Accounting & Finance'),
        ('transaction', 'Transactions'),
        ('generic', 'Generic Custom Model')
    ], string='Category', default='master', required=True)
    model = fields.Char(string='Target Model Name', required=True, help='e.g. res.partner, product.template')
    unique_key = fields.Char(string='Default Unique Key Field', default='name', help='Field used as unique identifier for upsert/matching')
    depends_on = fields.Char(string='Dependencies', help='Comma-separated codes of prerequisite data types')
    bridge_module = fields.Char(string='Bridge Module', default='core', help='Module providing this type, e.g. product, stock, account')
    is_fast_eligible = fields.Boolean(string='Fast Mode Eligible (Lightning)', default=False)
    is_composite = fields.Boolean(string='Is Composite Model', default=False)
    template_filename = fields.Char(string='Template File Name')
    template_data = fields.Binary(string='Template File (CSV/XLSX)', attachment=True)
    description = fields.Text(string='Description / Instructions')
    is_installed = fields.Boolean(string='Is Bridge Available', compute='_compute_is_installed', store=False)

    def _compute_is_installed(self):
        for rec in self:
            if rec.bridge_module in ('core', 'base'):
                rec.is_installed = True
            elif rec.model and rec.model in self.env:
                rec.is_installed = True
            else:
                rec.is_installed = False
