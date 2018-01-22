#!/usr/bin/env python
# -*- coding: utf-8 -*- #
from __future__ import unicode_literals

AUTHOR = u'Nical'
AUTHOR_NAME='Nicolas Silva'
SITENAME = u'Eight million pixels and counting'
SITEURL = ''

PATH = 'content'

TIMEZONE = 'Europe/Paris'

DEFAULT_LANG = u'en'

# Feed generation is usually not desired when developing
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None
THEME='theme/svbhack'
ARTICLE_PATHS = ['posts', 'images']
PAGE_PATHS = ['pages', 'images']
STATIC_PATHS = ['images']
ARTICLE_URL = 'posts/{slug}.html'
ARTICLE_SAVE_AS = 'posts/{slug}.html'

# aside
LINKS = ()
SOCIAL = (
    ('mastodon', 'https://mastodon.gamedev.place/@Nical'),
    ('twitter', 'https://twitter.com/nicalsilva'),
    ('github', 'https://github.com/nical'),
    ('mozgfx', 'http://mozillagfx.wordpress.com/'),
)

DISPLAY_PAGES_ON_MENU = False

DEFAULT_PAGINATION = False

# Uncomment following line if you want document-relative URLs when developing
#RELATIVE_URLS = True
