Changelog
=========

Date: 2026-06-25 (Thursday) at 12:15 AM
Changes:
- Created Odoo 18 AWS S3 Integration module with full manifest settings (odoofusion_aws_s3_integration/__manifest__.py)
- Implemented models for S3 bucket connection, configuration rules, activity log terminal, visual dashboard, and S3 file explorer (odoofusion_aws_s3_integration/models/)
- Overrode ir.attachment model to handle auto attachment sync and storage logic (odoofusion_aws_s3_integration/models/ir_attachment.py)
- Configured security access settings (odoofusion_aws_s3_integration/security/ir.model.access.csv)
- Created views for dashboard, file explorer, configurations, and logs (odoofusion_aws_s3_integration/views/)

Date: 2026-06-25 (Thursday) at 11:54 AM
Changes:
- Fixed ValueError: added ondelete='cascade' to model_id Many2one(ir.model) in AwsS3AttachmentRule — ir.model comodel does not support restrict mode (aws_s3_attachment_rule.py)
- Added missing action_open_dashboard() @api.model method to AwsS3Dashboard referenced by ir.actions.server in XML (aws_s3_dashboard.py)
- Rewrote ir_attachment.py: fixed @api.model _file_read accessing instance fields (is_s3_stored) on model level, removed unused new_vals_list in create(), fixed dual-storage self-healing fallback to search by store_fname not self, added _get_active_s3_rule() helper (ir_attachment.py)

Date: 2026-07-14 (Tuesday) at 12:24 AM
Changes:
- Generated comprehensive PDF technical reference and user guide manual (doc/aws_s3_integration_guide.pdf)

Date: 2026-07-16 (Thursday) at 11:08 PM
Changes:
- Created AWS S3 bucket credentials and sale order sync rule data record (data/aws_s3_data.xml)
- Declared dependency on the sale module and registered the new data file (__manifest__.py)
- Restricted attachment sync rules configuration to sale.order model (models/aws_s3_attachment_rule.py)
- Restricted ir.attachment active rule lookup to sale.order model (models/ir_attachment.py)

Date: 2026-07-16 (Thursday) at 11:46 PM
Changes:
- Upgraded dashboard layout and logic to feature dynamic metrics, recent uploads table, live sync efficiency gauge, and direct navigational shortcuts (models/aws_s3_dashboard.py)
- Streamlined dashboard form view by removing redundant bottom buttons (views/aws_s3_dashboard_views.xml)

Date: 2026-07-16 (Thursday) at 11:51 PM
Changes:
- Refactored dashboard HTML to utilize native Bootstrap 5 classes, overcoming Odoo's HTML sanitizer stylesheet stripping (models/aws_s3_dashboard.py)

Date: 2026-07-16 (Thursday) at 11:54 PM
Changes:
- Implemented high-contrast color scheme and styled action buttons inline for enhanced visibility (models/aws_s3_dashboard.py)

Date: 2026-07-16 (Thursday) at 11:57 PM
Changes:
- Replaced S3 Key column text-truncation with word-break wrapping for complete path readability (models/aws_s3_dashboard.py)

Date: 2026-07-16 (Thursday) at 11:59 PM
Changes:
- Changed S3 Key text color to high-contrast slate color for readability in light mode (models/aws_s3_dashboard.py)

Date: 2026-07-17 (Friday) at 12:05 AM
Changes:
- Updated module author to 'OdooFusion' and added website link (__manifest__.py)
- Generated and set a new world-class flat vector app icon (static/description/icon.png)

Date: 2026-07-17 (Friday) at 12:10 AM
Changes:
- Created world-class Odoo App Store documentation (static/description/index.html)

Date: 2026-07-17 (Friday) at 12:15 AM
Changes:
- Replaced light-grey text classes in App Store description with high-contrast colors (#334155 / #475569) (static/description/index.html)

Date: 2026-07-17 (Friday) at 12:18 AM
Changes:
- Fixed datetime timezone-aware exception by converting LastModified from boto3 to timezone-naive (models/aws_s3_file_explorer.py)

Date: 2026-07-17 (Friday) at 12:23 AM
Changes:
- Resolved 'Please save your changes first' wizard warning by persisting transient explorer records on load (models/aws_s3_file_explorer.py, views/aws_s3_file_explorer_views.xml, views/menuitems.xml, models/aws_s3_dashboard.py)

Date: 2026-07-17 (Friday) at 12:31 AM
Changes:
- Removed model-level sale.order restriction to allow S3 sync configurations for all persistent models (models/aws_s3_attachment_rule.py, models/ir_attachment.py)

Date: 2026-07-17 (Friday) at 12:34 AM
Changes:
- Removed hard dependency on sale module from manifest and switched default rule to res.partner (__manifest__.py, data/aws_s3_data.xml)
