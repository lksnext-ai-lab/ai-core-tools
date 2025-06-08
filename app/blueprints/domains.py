from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from extensions import db
from model.domain import Domain
from model.url import Url
from flask_paginate import Pagination, get_page_args
from services.embedding_service_service import EmbeddingServiceService
from services.silo_service import SiloService
from tools import scrapTools
from services.url_service import UrlService
from services.domain_service import DomainService
from utils.pricing_decorators import check_usage_limit
domains_blueprint = Blueprint('domains', __name__, url_prefix='/domains')

LIST_TEMPLATE = 'domains.domains'
@domains_blueprint.route('/', methods=['GET'])
def domains():
    app_id = session.get('app_id')
    domains = DomainService.get_domains_by_app_id(app_id)
    return render_template('domains/list.html', domains=domains)

def _check_domain_creation_limit():
    """Helper function to check domain creation limits"""
    from services.subscription_service import SubscriptionService
    user_id = session.get('user_id')
    if user_id:
        usage_check = SubscriptionService.check_usage_limits(user_id, 'domains')
        if not usage_check['allowed']:
            flash(f"Domain limit exceeded. Current plan allows {usage_check.get('limit', 0)} domains. Please upgrade your plan to continue.", 'warning')
            return redirect(url_for('subscription.dashboard'))
    return None

@domains_blueprint.route('/<int:domain_id>', methods=['GET', 'POST'])
def domain(domain_id):
    if request.method == 'POST':
        form_data = request.form.copy()
        form_data['app_id'] = session['app_id']
        
        # Check if this is a new domain creation (domain_id is 0 or None)
        if domain_id == 0 or domain_id is None:
            limit_check = _check_domain_creation_limit()
            if limit_check:
                return limit_check
        
        embedding_service_id = form_data.pop('embedding_service_id', None)
        
        DomainService.create_or_update_domain(Domain(**form_data), embedding_service_id)
        return redirect(url_for(LIST_TEMPLATE))
    else:
        embedding_services = EmbeddingServiceService.get_embedding_services_by_app_id(session['app_id'])
        if domain_id is None or domain_id == 0:
            domain = Domain(domain_id=0)
        else:
            domain = DomainService.get_domain(domain_id)
        return render_template('domains/domain.html', domain=domain, embedding_services=embedding_services)
    
@domains_blueprint.route('/<int:domain_id>/delete', methods=['GET'])
def domain_delete(domain_id):
    domain = DomainService.get_domain(domain_id)
    DomainService.delete_domain(domain)
    return redirect(url_for(LIST_TEMPLATE))


@domains_blueprint.route('/<int:domain_id>/urls', methods=['GET'])
def view_domain_urls(domain_id):
    page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
    domain = db.session.query(Domain).filter(Domain.domain_id == domain_id).first()
    urls = domain.urls[offset: offset + per_page]
    pagination = Pagination(page=page, per_page=per_page, total=len(domain.urls), css_framework='bootstrap5')
    return render_template('domains/url_list.html', domain=domain, urls=urls, pagination=pagination)


@domains_blueprint.route('/<int:domain_id>/urls/add', methods=['POST'])
def add_url(domain_id):
    url_value = request.form['url'].split('?')[0]
    domain = db.session.query(Domain).filter(Domain.domain_id == domain_id).first()
    UrlService.create_url(url_value, domain.domain_id)
    content = scrapTools.get_text_from_url(domain.base_url + url_value)
    SiloService.index_single_content(domain.silo_id, content, {"url": domain.base_url + url_value})
    return redirect(url_for('domains.view_domain_urls', domain_id=domain.domain_id))

@domains_blueprint.route('/domain/create', methods=['POST'])
@check_usage_limit('domains')
def create_domain():
    try:
        # Create Pydantic model from form data
        form_data = {
            "name": request.form['name'],
            "description": request.form.get('description'),
            "base_url": request.form['base_url'],
            "content_tag": request.form.get('content_tag'),
            "content_class": request.form.get('content_class'),
            "content_id": request.form.get('content_id'),
            "app_id": request.form.get('app_id', type=int),
            "silo_id": request.form.get('silo_id', type=int)
        }
        
        DomainService.create_or_update_domain(Domain(**form_data))
        flash('Domain created successfully!', 'success')
        return redirect(url_for(LIST_TEMPLATE))
    except Exception as e:
        # Handle validation errors or other exceptions
        flash(f'Error creating domain: {str(e)}', 'error')
        return redirect(url_for(LIST_TEMPLATE))

@domains_blueprint.route('/<int:domain_id>/url/<int:url_id>/delete', methods=['GET'])
def delete_url(domain_id, url_id):
    UrlService.delete_url(url_id, domain_id)
    return redirect(url_for('domains.view_domain_urls', domain_id=domain_id))

