from flask import Blueprint, render_template, request, redirect, url_for
from app.extensions import db
from app.model.domain import Domain
from app.model.url import Url
from flask_paginate import Pagination, get_page_args
from app.services.silo_service import SiloService
from app.tools import scrapTools
from app.services.url_service import UrlService
crawler_blueprint = Blueprint('crawler', __name__, url_prefix='/crawlers')

@crawler_blueprint.route('/', methods=['GET'])
def crawlers():
    domains = db.session.query(Domain).all()
    return render_template('crawlers/list.html', domains=domains)

@crawler_blueprint.route('/<int:crawler_id>', methods=['GET'])
def crawler(crawler_id):
    return render_template('crawlers/crawler.html', crawler_id=crawler_id)

@crawler_blueprint.route('/<int:domain_id>/urls', methods=['GET'])
def view_domain_urls(domain_id):
    page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
    domain = db.session.query(Domain).filter(Domain.domain_id == domain_id).first()
    urls = domain.urls[offset: offset + per_page]
    pagination = Pagination(page=page, per_page=per_page, total=len(domain.urls), css_framework='bootstrap5')
    return render_template('crawlers/url_list.html', domain=domain, urls=urls, pagination=pagination)


@crawler_blueprint.route('/<int:domain_id>/urls/add', methods=['POST'])
def add_url(domain_id):
    urlValue = request.form['url'].split('?')[0]
    domain = db.session.query(Domain).filter(Domain.domain_id == domain_id).first()
    url = UrlService.create_url(urlValue, domain.domain_id)
    content = scrapTools.get_text_from_url(domain.base_url + urlValue)
    SiloService.index_content(domain.silo_id, content, {"url": domain.base_url + urlValue})
    return redirect(url_for('crawler.view_domain_urls', domain_id=domain.domain_id))

