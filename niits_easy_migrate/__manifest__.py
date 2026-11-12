# -*- coding: utf-8 -*-
{
    'name': "Easy Data Migration Studio",
    'summary': "High-performance, safe, resumable, and one-click undo data migration studio for CSV/XLSX imports",
    'description': """
Data Migration Studio for Odoo 17 Community Edition
===================================================
Streamline your ERP data import and migration with blazing speed and complete safety:

* **Interactive 4-Step Studio Wizard**: Source selection, smart column auto-mapping, engine options, and pre-validation review.
* **19 Supported Data Types**: Pre-defined dependency order covering Master Data, Inventory, Accounting, and Transactions.
* **Smart Auto-Mapping**: Automatic field detection with fuzzy matching across labels, technical field names, and synonyms.
* **Validate Before You Write**: Full dry-run simulation and downloadable error reports before any database commit.
* **Parallel & Resumable Engine**: Chunked batch processing with automatic checkpointing and restart resilience.
* **One-Click Undo**: Instant rollback of all created and modified records in reverse dependency sequence.
* **Optimized ORM Engine**: High throughput batch creation with disable tracking flags and pre-resolved reference caching.
* **Sample Packs**: Ready-to-use numbered sample CSV templates (01 to 19) for seamless testing.
    """,
    'author': "Arif N Ramadhan",
    'website': "https://www.niits.id",
    'category': 'Extra Tools',
    'version': '17.0.1.0.0',
    'license': 'OPL-1',
    'price': 0.00,
    'currency': 'EUR',
    'depends': [
        'base',
        'web',
        'mail',
    ],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/migrate_type_data.xml',
        'data/migrate_sample_data.xml',
        'data/ir_cron_data.xml',
        'views/migrate_type_views.xml',
        'views/migrate_mapping_views.xml',
        'views/migrate_job_views.xml',
        'views/migrate_wizard_views.xml',
        'views/migrate_sample_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'niits_easy_migrate/static/src/scss/migrate_studio.scss',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
