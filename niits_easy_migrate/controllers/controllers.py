# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class NiitsEasyMigrateController(http.Controller):

    @http.route('/niits_easy_migrate/get_dashboard_data', type='json', auth='user')
    def get_dashboard_data(self):
        """Aggregate stats for Dashboard (KPIs, active jobs, recent history)."""
        Job = request.env['niits.migrate.job']
        Type = request.env['niits.migrate.type']

        # Total counts
        total_jobs = Job.search_count([])
        done_jobs = Job.search_count([('state', '=', 'done')])
        running_jobs = Job.search_count([('state', '=', 'running')])
        failed_jobs = Job.search_count([('state', '=', 'failed')])

        recent_jobs = Job.search_read(
            [],
            fields=['name', 'source_filename', 'state', 'total_rows', 'done_rows', 'failed_rows', 'duration_str', 'create_date'],
            order='id desc',
            limit=10
        )

        types = Type.search_read(
            [],
            fields=['id', 'name', 'code', 'category', 'sequence', 'is_fast_eligible', 'bridge_module'],
            order='sequence, id'
        )

        return {
            'kpi': {
                'total_jobs': total_jobs,
                'done_jobs': done_jobs,
                'running_jobs': running_jobs,
                'failed_jobs': failed_jobs,
            },
            'recent_jobs': recent_jobs,
            'types': types,
        }
