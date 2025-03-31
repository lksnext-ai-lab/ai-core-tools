from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from services.mcp_config_service import MCPConfigService
from model.mcp_config import TransportType
from flask_login import login_required

mcp_configs = Blueprint('mcp_configs', __name__)

@mcp_configs.route('/app/<int:app_id>/mcp_configs')
@login_required
def app_mcp_configs(app_id):
    """List all MCP configs for an app"""
    configs = MCPConfigService.get_mcp_configs(app_id)
    return render_template('mcp_configs/list.html', configs=configs, app_id=app_id)

@mcp_configs.route('/app/<int:app_id>/mcp_configs/new', methods=['GET', 'POST'])
@login_required
def new_mcp_config(app_id):
    """Create a new MCP config"""
    if request.method == 'POST':
        try:
            config_data = request.form.to_dict()
            config_data['app_id'] = app_id
            MCPConfigService.validate_mcp_config(config_data)
            MCPConfigService.create_or_update_mcp_config(config_data)
            flash('MCP config created successfully', 'success')
            return redirect(url_for('mcp_configs.app_mcp_configs', app_id=app_id))
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash('An error occurred while creating the MCP config', 'error')
    
    return render_template('mcp_configs/mcp_config_form.html', app_id=app_id, transport_types=list(TransportType))

@mcp_configs.route('/app/<int:app_id>/mcp_configs/<int:config_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_mcp_config(app_id, config_id):
    """Edit an existing MCP config"""
    mcp_config = MCPConfigService.get_mcp_config(config_id)
    if not mcp_config:
        flash('MCP config not found', 'error')
        return redirect(url_for('mcp_configs.app_mcp_configs', app_id=app_id))
    
    if request.method == 'POST':
        try:
            config_data = request.form.to_dict()
            config_data['config_id'] = config_id
            config_data['app_id'] = app_id
            MCPConfigService.validate_mcp_config(config_data)
            MCPConfigService.create_or_update_mcp_config(config_data)
            flash('MCP config updated successfully', 'success')
            return redirect(url_for('mcp_configs.app_mcp_configs', app_id=app_id))
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash('An error occurred while updating the MCP config', 'error')
    
    return render_template('mcp_configs/mcp_config_form.html', mcp_config=mcp_config, app_id=app_id, transport_types=list(TransportType))

@mcp_configs.route('/app/<int:app_id>/mcp_configs/<int:config_id>/delete', methods=['POST'])
@login_required
def delete_mcp_config(app_id, config_id):
    """Delete an MCP config"""
    try:
        MCPConfigService.delete_mcp_config(config_id)
        flash('MCP config deleted successfully', 'success')
    except Exception as e:
        flash('An error occurred while deleting the MCP config', 'error')
    
    return redirect(url_for('mcp_configs.app_mcp_configs', app_id=app_id)) 