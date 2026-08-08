# -*- coding: utf-8 -*-
# Author: Metamorphosis, Joyanto

from odoo import models, fields, api


class AwsS3Dashboard(models.TransientModel):
    _name = 'aws.s3.dashboard'
    _description = 'AWS S3 Sync Dashboard'

    name = fields.Char(string='Dashboard Name', default='AWS S3 Sync Monitor')
    
    # KPIs
    bucket_count = fields.Integer(string='Bucket Count', compute='_compute_metrics')
    active_rule_count = fields.Integer(string='Active Sync Rules', compute='_compute_metrics')
    success_sync_count = fields.Integer(string='Successful Syncs', compute='_compute_metrics')
    failed_sync_count = fields.Integer(string='Failed Syncs', compute='_compute_metrics')
    
    # HTML Grid for visual widgets
    kpi_card_html = fields.Html(string='KPI Display', compute='_compute_kpi_card_html')

    def _compute_metrics(self):
        for dash in self:
            dash.bucket_count = self.env['aws.s3.bucket'].search_count([])
            dash.active_rule_count = self.env['aws.s3.attachment.rule'].search_count([('is_active', '=', True)])
            dash.success_sync_count = self.env['aws.s3.log'].search_count([('status', '=', 'success')])
            dash.failed_sync_count = self.env['aws.s3.log'].search_count([('status', '=', 'failed')])

    def _compute_kpi_card_html(self):
        for dash in self:
            dash._compute_metrics()
            
            total_syncs = dash.success_sync_count + dash.failed_sync_count
            success_rate = round((dash.success_sync_count / total_syncs) * 100, 1) if total_syncs > 0 else 100.0
            
            recent_logs = self.env['aws.s3.log'].sudo().search([], limit=5)
            logs_html = ""
            if recent_logs:
                for log in recent_logs:
                    filename = log.attachment_name or 'file'
                    ext = filename.split('.')[-1].lower() if '.' in filename else ''
                    
                    if ext in ['xlsx', 'xls', 'csv']:
                        icon = 'fa-file-excel-o text-success'
                    elif ext == 'pdf':
                        icon = 'fa-file-pdf-o text-danger'
                    elif ext in ['png', 'jpg', 'jpeg', 'gif', 'svg']:
                        icon = 'fa-file-image-o text-primary'
                    elif ext in ['doc', 'docx']:
                        icon = 'fa-file-word-o text-info'
                    else:
                        icon = 'fa-file-o text-secondary'
                        
                    badge_style = "background-color: #dcfce7; color: #15803d; border: 1px solid #bbf7d0;" if log.status == 'success' else "background-color: #fee2e2; color: #b91c1c; border: 1px solid #fecaca;"
                    status_text = "Success" if log.status == 'success' else "Failed"
                    
                    if log.res_model and log.res_id:
                        record_link = f'<a href="/web#model={log.res_model}&amp;id={log.res_id}&amp;view_type=form" class="fw-bold text-decoration-none text-primary" style="color: #0284c7 !important;" title="Click to view Odoo record"><i class="fa fa-external-link me-1"></i>{log.res_model} ({log.res_id})</a>'
                    else:
                        record_link = '<span class="text-muted">N/A</span>'
                        
                    s3_path = log.s3_key or ''
                    time_str = log.create_date.strftime('%Y-%m-%d %H:%M') if log.create_date else 'N/A'
                    
                    logs_html += f"""
                    <tr>
                        <td class="fw-bold" style="word-break: break-word; color: #1e293b;"><i class="fa {icon} me-2"></i>{filename}</td>
                        <td style="word-break: break-word;">{record_link}</td>
                        <td style="font-family: monospace; font-size: 11px; word-break: break-all; color: #334155;" title="{s3_path}">{s3_path}</td>
                        <td><span class="badge rounded-pill" style="{badge_style}">{status_text}</span></td>
                        <td style="font-size: 11px; white-space: nowrap; color: #475569;">{time_str}</td>
                    </tr>
                    """
            else:
                logs_html = """
                <tr>
                    <td colspan="5" class="text-center text-muted py-4">
                        <i class="fa fa-inbox fa-2x mb-2 d-block"></i>No sync activity recorded yet.
                    </td>
                </tr>
                """
                
            buckets = self.env['aws.s3.bucket'].sudo().search([])
            buckets_html = ""
            if buckets:
                for bucket in buckets:
                    if bucket.state == 'connected':
                        state_badge = '<span class="badge rounded-pill" style="background-color: #dcfce7; color: #15803d; border: 1px solid #bbf7d0;"><i class="fa fa-check-circle me-1"></i>Connected</span>'
                    elif bucket.state == 'failed':
                        state_badge = '<span class="badge rounded-pill" style="background-color: #fee2e2; color: #b91c1c; border: 1px solid #fecaca;"><i class="fa fa-exclamation-triangle me-1"></i>Failed</span>'
                    else:
                        state_badge = '<span class="badge rounded-pill" style="background-color: #fef3c7; color: #d97706; border: 1px solid #fde68a;"><i class="fa fa-clock-o me-1"></i>Not Tested</span>'
                        
                    bucket_link = f'/web#model=aws.s3.bucket&amp;id={bucket.id}&amp;view_type=form'
                    
                    buckets_html += f"""
                    <div class="border rounded p-3 mb-2 d-flex justify-content-between align-items-center shadow-sm bg-white" style="border-color: #e2e8f0 !important;">
                        <div>
                            <div class="fw-bold text-dark" style="font-size: 13px;"><i class="fa fa-hdd-o text-primary me-2"></i>{bucket.name}</div>
                            <div class="text-muted" style="font-size: 11px; margin-left: 20px;">Region: {bucket.region_name}</div>
                        </div>
                        <div class="d-flex align-items-center gap-2">
                            {state_badge}
                            <a href="{bucket_link}" class="btn btn-outline-secondary btn-sm p-1 px-2 fw-bold text-dark border-secondary bg-white"><i class="fa fa-pencil"></i></a>
                        </div>
                    </div>
                    """
            else:
                buckets_html = """
                <div class="text-center text-muted py-3">
                    <i class="fa fa-database fa-2x mb-2 d-block"></i>No S3 Buckets configured.
                </div>
                """

            html = f"""
            <div class="container-fluid p-0" style="font-family: 'Outfit', 'Segoe UI', Roboto, sans-serif;">
                
                <div class="d-flex justify-content-between align-items-center mb-4 pb-3 border-bottom flex-wrap gap-3">
                    <h4 class="mb-0 fw-bold" style="color: #2c3e50;"><i class="fa fa-cloud text-primary me-2"></i>AWS S3 Sync Monitor (Odoo 19)</h4>
                    <div class="d-flex gap-2 flex-wrap">
                        <a href="/web#action=odoofusion_aws_s3_integration.action_aws_s3_file_explorer_server" class="btn btn-sm fw-bold shadow-sm" style="background-color: #4f46e5; color: #ffffff; border: 1px solid #4f46e5; padding: 6px 12px; border-radius: 6px;"><i class="fa fa-folder-open me-1"></i> S3 File Explorer</a>
                        <a href="/web#action=odoofusion_aws_s3_integration.action_aws_s3_bucket" class="btn btn-sm fw-bold shadow-sm" style="background-color: #ffffff; color: #334155; border: 1px solid #cbd5e1; padding: 6px 12px; border-radius: 6px;"><i class="fa fa-database me-1"></i> Setup Buckets</a>
                        <a href="/web#action=odoofusion_aws_s3_integration.action_aws_s3_attachment_rule" class="btn btn-sm fw-bold shadow-sm" style="background-color: #ffffff; color: #334155; border: 1px solid #cbd5e1; padding: 6px 12px; border-radius: 6px;"><i class="fa fa-cogs me-1"></i> Sync Rules</a>
                        <a href="/web#action=odoofusion_aws_s3_integration.action_aws_s3_log" class="btn btn-sm fw-bold shadow-sm" style="background-color: #ffffff; color: #334155; border: 1px solid #cbd5e1; padding: 6px 12px; border-radius: 6px;"><i class="fa fa-file-text-o me-1"></i> Audit Logs</a>
                    </div>
                </div>

                <div class="row g-3 mb-4">
                    <div class="col-12 col-sm-6 col-md-3">
                        <div class="card h-100 border shadow-sm position-relative" style="background-color: #f5f3ff; border-color: #ddd6fe !important; border-radius: 12px;">
                            <div class="card-body d-flex align-items-center">
                                <div class="rounded-3 p-3 me-3 d-flex align-items-center justify-content-center" style="width: 48px; height: 48px; background-color: #ddd6fe; color: #6d28d9;">
                                    <i class="fa fa-database fa-lg"></i>
                                </div>
                                <div>
                                    <div class="text-uppercase fw-bold" style="font-size: 10px; letter-spacing: 0.5px; color: #6d28d9;">Buckets</div>
                                    <h3 class="mb-0 fw-bold" style="color: #4c1d95; font-size: 26px;">{dash.bucket_count}</h3>
                                    <small style="font-size: 11px; color: #7c3aed;">Active AWS Buckets</small>
                                </div>
                            </div>
                            <a href="/web#action=odoofusion_aws_s3_integration.action_aws_s3_bucket" class="stretched-link"></a>
                        </div>
                    </div>

                    <div class="col-12 col-sm-6 col-md-3">
                        <div class="card h-100 border shadow-sm position-relative" style="background-color: #ecfeff; border-color: #a5f3fc !important; border-radius: 12px;">
                            <div class="card-body d-flex align-items-center">
                                <div class="rounded-3 p-3 me-3 d-flex align-items-center justify-content-center" style="width: 48px; height: 48px; background-color: #a5f3fc; color: #0891b2;">
                                    <i class="fa fa-filter fa-lg"></i>
                                </div>
                                <div>
                                    <div class="text-uppercase fw-bold" style="font-size: 10px; letter-spacing: 0.5px; color: #0891b2;">Active Rules</div>
                                    <h3 class="mb-0 fw-bold" style="color: #164e63; font-size: 26px;">{dash.active_rule_count}</h3>
                                    <small style="font-size: 11px; color: #0e7490;">Sync configurations</small>
                                </div>
                            </div>
                            <a href="/web#action=odoofusion_aws_s3_integration.action_aws_s3_attachment_rule" class="stretched-link"></a>
                        </div>
                    </div>

                    <div class="col-12 col-sm-6 col-md-3">
                        <div class="card h-100 border shadow-sm position-relative" style="background-color: #f0fdf4; border-color: #bbf7d0 !important; border-radius: 12px;">
                            <div class="card-body d-flex align-items-center">
                                <div class="rounded-3 p-3 me-3 d-flex align-items-center justify-content-center" style="width: 48px; height: 48px; background-color: #bbf7d0; color: #15803d;">
                                    <i class="fa fa-check-circle fa-lg"></i>
                                </div>
                                <div>
                                    <div class="text-uppercase fw-bold" style="font-size: 10px; letter-spacing: 0.5px; color: #15803d;">Success Syncs</div>
                                    <h3 class="mb-0 fw-bold" style="color: #166534; font-size: 26px;">{dash.success_sync_count}</h3>
                                    <small style="font-size: 11px; color: #15803d;">Successful uploads</small>
                                </div>
                            </div>
                            <a href="/web#action=odoofusion_aws_s3_integration.action_aws_s3_log" class="stretched-link"></a>
                        </div>
                    </div>

                    <div class="col-12 col-sm-6 col-md-3">
                        <div class="card h-100 border shadow-sm position-relative" style="background-color: #fef2f2; border-color: #fecaca !important; border-radius: 12px;">
                            <div class="card-body d-flex align-items-center">
                                <div class="rounded-3 p-3 me-3 d-flex align-items-center justify-content-center" style="width: 48px; height: 48px; background-color: #fecaca; color: #b91c1c;">
                                    <i class="fa fa-exclamation-triangle fa-lg"></i>
                                </div>
                                <div>
                                    <div class="text-uppercase fw-bold" style="font-size: 10px; letter-spacing: 0.5px; color: #b91c1c;">Failures</div>
                                    <h3 class="mb-0 fw-bold" style="color: #991b1b; font-size: 26px;">{dash.failed_sync_count}</h3>
                                    <small style="font-size: 11px; color: #b91c1c;">Sync issues</small>
                                </div>
                            </div>
                            <a href="/web#action=odoofusion_aws_s3_integration.action_aws_s3_log" class="stretched-link"></a>
                        </div>
                    </div>
                </div>

                <div class="row g-4">
                    <div class="col-12 col-lg-8">
                        <div class="card border shadow-sm h-100" style="border-radius: 12px; border-color: #e2e8f0 !important;">
                            <div class="card-header bg-white border-bottom-0 pt-3 px-3 pb-0 d-flex justify-content-between align-items-center">
                                <h5 class="card-title mb-0 fw-bold" style="font-size: 15px; color: #2c3e50;"><i class="fa fa-history text-info me-2"></i>Recent Sync Logs</h5>
                                <a href="/web#action=odoofusion_aws_s3_integration.action_aws_s3_log" class="btn btn-link btn-sm text-decoration-none p-0 fw-bold text-primary">View All &rarr;</a>
                            </div>
                            <div class="card-body p-3">
                                <div class="table-responsive">
                                    <table class="table table-hover align-middle mb-0" style="font-size: 13px;">
                                        <thead class="table-light">
                                            <tr>
                                                <th style="color: #475569;">File Name</th>
                                                <th style="color: #475569;">Odoo Record</th>
                                                <th style="color: #475569;">S3 Key</th>
                                                <th style="color: #475569;">Status</th>
                                                <th style="color: #475569;">Sync Time</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {logs_html}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="col-12 col-lg-4">
                        <div class="d-flex flex-column gap-4">
                            <div class="card border shadow-sm text-center" style="border-radius: 12px; background-color: #fff; border-color: #e2e8f0 !important;">
                                <div class="card-body py-4">
                                    <h6 class="text-uppercase fw-bold mb-3" style="font-size: 11px; letter-spacing: 0.5px; color: #b45309;"><i class="fa fa-bolt text-warning me-1"></i>Sync Efficiency</h6>
                                    <div class="d-flex justify-content-center align-items-center mb-3">
                                        <div class="progress" style="width: 85%; height: 20px; border-radius: 10px; background-color: #e2e8f0;">
                                            <div class="progress-bar bg-success progress-bar-striped progress-bar-animated fw-bold" role="progressbar" style="width: {success_rate}%; font-size: 11px; line-height: 20px; border-radius: 10px;" aria-valuenow="{success_rate}" aria-valuemin="0" aria-valuemax="100">
                                                {success_rate}%
                                            </div>
                                        </div>
                                    </div>
                                    <small class="text-muted">{dash.success_sync_count} out of {total_syncs} uploads completed successfully.</small>
                                </div>
                            </div>

                            <div class="card border shadow-sm" style="border-radius: 12px; background-color: #fff; border-color: #e2e8f0 !important;">
                                <div class="card-header bg-white border-bottom-0 pt-3 px-3 pb-0 d-flex justify-content-between align-items-center">
                                    <h6 class="card-title mb-0 fw-bold" style="font-size: 14px; color: #2c3e50;"><i class="fa fa-hdd-o text-primary me-2"></i>Active Buckets</h6>
                                    <a href="/web#action=odoofusion_aws_s3_integration.action_aws_s3_bucket" class="btn btn-link btn-sm text-decoration-none p-0 fw-bold text-primary">Manage &rarr;</a>
                                </div>
                                <div class="card-body p-3">
                                    {buckets_html}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            """
            dash.kpi_card_html = html

    def action_view_logs(self):
        return {
            'name': 'Activity Logs',
            'type': 'ir.actions.act_window',
            'res_model': 'aws.s3.log',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_view_buckets(self):
        return {
            'name': 'AWS S3 Buckets',
            'type': 'ir.actions.act_window',
            'res_model': 'aws.s3.bucket',
            'view_mode': 'list,form',
            'target': 'current',
        }

    @api.model
    def action_open_dashboard(self):
        record = self.create({})
        return {
            'name': 'AWS S3 Dashboard',
            'type': 'ir.actions.act_window',
            'res_model': 'aws.s3.dashboard',
            'res_id': record.id,
            'view_mode': 'form',
            'target': 'main',
        }
