Changelog
=========

Date: 2026-08-08 (Saturday) at 10:00 PM
Changes:
- Converted module architecture and manifests to Odoo 19 (version 19.0.2.0.0) with author Metamorphosis, Joyanto (odoofusion_aws_s3_integration/__manifest__.py)
- Ported models for global S3 config, ir.attachment storage engine hooks (_file_write, _file_read, _file_delete, _to_http_stream), transactional deletion queue, background migration wizard, dashboard, and S3 file explorer to Odoo 19 ORM standards (odoofusion_aws_s3_integration/models/)
- Created XML views enforcing <list> tag for list views, view_mode="list,form", attachment status banners, and navigation menus for Odoo 19 (odoofusion_aws_s3_integration/views/)
- Configured security access control lists and scheduled actions (odoofusion_aws_s3_integration/security/ir.model.access.csv, odoofusion_aws_s3_integration/data/)

Date: 2026-08-08 (Saturday) at 10:19 PM
Changes:
- Fixed ParseError on module installation: reordered data files list in manifest so aws_s3_attachment_rule_views.xml loads before aws_s3_config_views.xml, resolving missing External ID action_aws_s3_attachment_rule (odoofusion_aws_s3_integration/__manifest__.py)

Date: 2026-08-08 (Saturday) at 10:23 PM
Changes:
- Fixed View ValidationError: added <field name="is_s3_stored" invisible="1"/> inside ir.attachment form view xpath before invisible modifier usage (views/ir_attachment_views.xml)

Date: 2026-08-08 (Saturday) at 10:31 PM
Changes:
- Fixed ModuleNotFoundError on module installation: removed top-level unused import boto3 from models/aws_s3_file_explorer.py and declared external_dependencies python boto3 in __manifest__.py (models/aws_s3_file_explorer.py, __manifest__.py)

Date: 2026-08-08 (Saturday) at 10:35 PM
Changes:
- Fixed AttributeError on module installation: replaced self.env['ir.attachment'].clear_caches() with self.env.registry.clear_cache() and updated create() method signatures to @api.model_create_multi (models/aws_s3_attachment_rule.py, models/aws_s3_config.py)

Date: 2026-08-08 (Saturday) at 10:44 PM
Changes:
- Fixed Invalid view aws.s3.log.search definition ParseError: replaced legacy expand="0" and string="Group By" attributes on search view group element with name="group_by" per Odoo 19 RNG schema specifications (views/aws_s3_log_views.xml)





