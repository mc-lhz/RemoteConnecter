from flask import Blueprint, render_template
import tempfile
import os
from flask import request, jsonify
from utils import *
update_bp = Blueprint('update', __name__)

@update_bp.route('/update')
def update_page():
    return render_template('update.html')

@update_bp.route('/api/update')
def update_api():
    updateUrl = request.args.get('updateUrl')
    success, message = update(updateUrl)
    if success:
        os._exit(0)
    else:
        return jsonify({'status': 'error', 'message': message})
    
