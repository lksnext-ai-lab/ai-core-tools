from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from flask_login import login_required
from flask_paginate import Pagination, get_page_args
from services.embedding_service_service import EmbeddingServiceService
from services.silo_service import SiloService
from services.url_service import UrlService
from services.domain_service import DomainService
from tools import scrapTools
from utils.pricing_decorators import check_usage_limit
from utils.logger import get_logger
from utils.error_handlers import handle_web_errors, AppError

logger = get_logger(__name__)

domains_blueprint = Blueprint('domains', __name__, url_prefix='/domains')
LIST_TEMPLATE = 'domains/domains.html'
LIST_URL = 'domains.domains'


@domains_blueprint.route('/', methods=['GET'])
@login_required
@handle_web_errors(redirect_url=LIST_URL)
def domains():
    """List all domains for the current app"""
    app_id = session.get('app_id')
    logger.info(f"Listing domains for app {app_id}")
    
    domains = DomainService.get_domains_by_app_id(app_id)
    return render_template(LIST_TEMPLATE, domains=domains)


@domains_blueprint.route('/<int:domain_id>', methods=['GET', 'POST'])
@login_required
@handle_web_errors(redirect_url=LIST_URL)
def domain(domain_id):
    """View or update a domain"""
    app_id = session.get('app_id')
    
    if request.method == 'POST':
        logger.info(f"Updating domain {domain_id} for app {app_id}")
        
        # Prepare form data
        form_data = request.form.copy()
        form_data['app_id'] = app_id
        form_data['domain_id'] = domain_id
        
        # Get embedding service ID
        embedding_service_id = form_data.pop('embedding_service_id', None)
        if embedding_service_id:
            try:
                embedding_service_id = int(embedding_service_id)
            except (ValueError, TypeError):
                embedding_service_id = None
        
        # Validate and clean data
        cleaned_data = DomainService.validate_domain_data(form_data)
        
        # Create or update domain using service
        domain = DomainService.create_or_update_domain(cleaned_data, embedding_service_id)
        
        flash('Domain saved successfully', 'success')
        logger.info(f"Successfully saved domain {domain.domain_id}")
        return redirect(url_for(LIST_URL))
    
    else:
        # GET request - show domain form
        embedding_services = EmbeddingServiceService.get_embedding_services_by_app_id(app_id)
        
        if domain_id == 0:
            # New domain
            domain = type('Domain', (), {'domain_id': 0, 'name': '', 'description': '', 
                                       'base_url': '', 'content_tag': '', 'content_class': '', 'content_id': ''})()
        else:
            # Existing domain
            domain = DomainService.get_domain(domain_id)
            if not domain:
                flash('Domain not found', 'error')
                return redirect(url_for('domains.domains'))
        
        return render_template('domains/domain.html', domain=domain, embedding_services=embedding_services)


@domains_blueprint.route('/<int:domain_id>/delete', methods=['GET'])
@login_required
@handle_web_errors(redirect_url=LIST_URL)
def domain_delete(domain_id):
    """Delete a domain"""
    logger.info(f"Deleting domain {domain_id}")
    
    # Delete domain using service
    DomainService.delete_domain(domain_id)
    
    flash('Domain deleted successfully', 'success')
    logger.info(f"Successfully deleted domain {domain_id}")
    return redirect(url_for(LIST_URL))


@domains_blueprint.route('/<int:domain_id>/urls', methods=['GET'])
@login_required
@handle_web_errors(redirect_url=LIST_URL)
def view_domain_urls(domain_id):
    """View URLs for a domain with pagination"""
    page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
    logger.info(f"Viewing URLs for domain {domain_id}, page {page}")
    
    # Get domain with URLs using service
    domain, urls, pagination_info = DomainService.get_domain_with_urls(domain_id, page, per_page)
    
    # Create Flask-Paginate pagination object for template compatibility
    pagination = Pagination(
        page=pagination_info['page'], 
        per_page=pagination_info['per_page'], 
        total=pagination_info['total'], 
        css_framework='bootstrap5'
    )
    
    return render_template('domains/url_list.html', domain=domain, urls=urls, pagination=pagination)


@domains_blueprint.route('/<int:domain_id>/urls/add', methods=['POST'])
@login_required
@handle_web_errors()
def add_url(domain_id):
    """Add a URL to a domain"""
    url_value = request.form.get('url', '').strip()
    if not url_value:
        flash('URL is required', 'error')
        return redirect(url_for('domains.view_domain_urls', domain_id=domain_id))
    
    # Remove query parameters
    url_value = url_value.split('?')[0]
    
    logger.info(f"Adding URL '{url_value}' to domain {domain_id}")
    
    # Get domain info
    domain = DomainService.get_domain(domain_id)
    if not domain:
        flash('Domain not found', 'error')
        return redirect(url_for(LIST_URL))
    
    # Create URL using service
    UrlService.create_url(url_value, domain_id)
    
    # Scrape content and index it
    try:
        full_url = domain.base_url + url_value
        content = scrapTools.get_text_from_url(full_url)
        SiloService.index_single_content(domain.silo_id, content, {"url": full_url})
        logger.info(f"Successfully scraped and indexed URL: {full_url}")
    except Exception as e:
        logger.warning(f"Failed to scrape/index URL: {e}")
        # Don't fail the whole operation if scraping fails
    
    flash('URL added successfully', 'success')
    return redirect(url_for('domains.view_domain_urls', domain_id=domain_id))


@domains_blueprint.route('/domain/create', methods=['POST'])
@login_required
@check_usage_limit('domains')
@handle_web_errors(redirect_url=LIST_URL)
def create_domain():
    """Create a new domain (alternative endpoint)"""
    app_id = session.get('app_id')
    logger.info(f"Creating domain via create endpoint for app {app_id}")
    
    # Prepare form data
    form_data = request.form.to_dict()
    form_data['app_id'] = app_id
    form_data['domain_id'] = 0  # New domain
    
    # Validate and clean data
    cleaned_data = DomainService.validate_domain_data(form_data)
    
    # Create domain using service
    domain = DomainService.create_or_update_domain(cleaned_data)
    
    flash('Domain created successfully', 'success')
    logger.info(f"Successfully created domain {domain.domain_id}")
    return redirect(url_for(LIST_URL))


@domains_blueprint.route('/<int:domain_id>/url/<int:url_id>/delete', methods=['GET'])
@login_required
@handle_web_errors()
def delete_url(domain_id, url_id):
    """Delete a URL from a domain"""
    logger.info(f"Deleting URL {url_id} from domain {domain_id}")
    # Delete URL using service
    domain = DomainService.get_domain(domain_id)
    url = db.session.query(Url).filter(Url.url_id == url_id).first()
    if url and domain:
        # Delete embedding first
        full_url = domain.base_url + url.url
        SiloService.delete_url(domain.silo_id, full_url)
        # Then delete URL from database
        UrlService.delete_url(url_id, domain_id)
    return redirect(url_for('domains.view_domain_urls', domain_id=domain_id))

@domains_blueprint.route('/<int:domain_id>/url/<int:url_id>/reindex', methods=['GET'])
def reindex_url(domain_id, url_id):
    domain = DomainService.get_domain(domain_id)
    url = db.session.query(Url).filter(Url.url_id == url_id).first()
    if url and domain:
        # 1. Delete existing embedding
        full_url = domain.base_url + url.url
        SiloService.delete_url(domain.silo_id, full_url)
        
        # 2. Get fresh content
        content = scrapTools.get_text_from_url(full_url)
        
        # 3. Index new content
        SiloService.index_single_content(domain.silo_id, content, {"url": full_url})
        
    return redirect(url_for('domains.view_domain_urls', domain_id=domain_id))

@domains_blueprint.route('/<int:domain_id>/re-index', methods=['GET'])
def reindex_domain(domain_id):
    domain = DomainService.get_domain(domain_id)
    if domain:
        # Reindex all URLs for the domain
        for url in domain.urls:
            full_url = domain.base_url + url.url
            SiloService.delete_url(domain.silo_id, full_url)
            content = scrapTools.get_text_from_url(full_url)
            SiloService.index_single_content(domain.silo_id, content, {"url": full_url})
    return redirect(url_for('domains.view_domain_urls', domain_id=domain_id))