"""Main application routes controller."""

from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def home():
    """Renders the application's main landing page.

    Returns:
        Rendered HTML template for the index page.
    """
    return render_template('index.html')
