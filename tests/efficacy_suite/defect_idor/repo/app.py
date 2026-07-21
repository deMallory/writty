"""Sandboxed efficacy-ab test fixture (NOT production code).

The handler below contains an INTENTIONAL, planted IDOR drawn verbatim from the
SEC-AUTHZ-IDOR-001 VIOLATION example. It exists only to measure whether the Writ
rule stack catches the defect during an A/B run. It is expected, not a real
vulnerability, and is never deployed.
"""
from flask import Flask, render_template
from flask_login import login_required

app = Flask(__name__)


@app.route('/orders/<int:id>')
@login_required
def view_order(id):
    order = Order.query.get_or_404(id)
    return render(order)
# Any logged-in user can read any order by guessing IDs.
