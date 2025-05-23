from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from models.kobayashi import (
    get_all_stories, get_story, create_story, update_story, delete_story,
    get_nodes_for_story, get_node, create_node, update_node, delete_node
)

kobayashi_bp = Blueprint('kobayashi', __name__, url_prefix='/kobayashi')

# --- Story CRUD ---
@kobayashi_bp.route('/stories')
@login_required
def stories():
    stories = get_all_stories()
    return render_template('kobayashi/stories.html', stories=stories)

@kobayashi_bp.route('/stories/new', methods=['GET', 'POST'])
@login_required
def create_story():
    if request.method == 'POST':
        title = request.form['title']
        intro = request.form['description']
        code = request.form['code']
        author = getattr(current_user, 'username', 'Unknown')
        from models.kobayashi import create_story as create_story_model
        create_story_model(title, intro, code, author)
        flash('Story created.', 'success')
        return redirect(url_for('kobayashi.stories'))
    return render_template('kobayashi/story_form.html', story=None)

@kobayashi_bp.route('/stories/<int:story_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_story(story_id):
    story = get_story(story_id)
    if not story:
        flash('Story not found.', 'danger')
        return redirect(url_for('kobayashi.stories'))
    if request.method == 'POST':
        title = request.form['title']
        intro = request.form['description']
        code = request.form['code']
        author = getattr(current_user, 'username', 'Unknown')
        from models.kobayashi import update_story as update_story_model
        update_story_model(story_id, title, intro, code, author)
        flash('Story updated.', 'success')
        return redirect(url_for('kobayashi.stories'))
    return render_template('kobayashi/story_form.html', story=story)

@kobayashi_bp.route('/stories/<int:story_id>/delete', methods=['POST'])
@login_required
def delete_story_route(story_id):
    delete_story(story_id)
    flash('Story deleted.', 'success')
    return redirect(url_for('kobayashi.stories'))

# --- Node CRUD ---
@kobayashi_bp.route('/stories/<int:story_id>/nodes')
@login_required
def nodes(story_id):
    story = get_story(story_id)
    if not story:
        flash('Story not found.', 'danger')
        return redirect(url_for('kobayashi.stories'))
    import json
    nodes = get_nodes_for_story(story_id)
    # Parse choices JSON for each node
    for node in nodes:
        if 'choices' in node and node['choices']:
            try:
                node['choices_dict'] = json.loads(node['choices'])
            except Exception:
                node['choices_dict'] = {}
        else:
            node['choices_dict'] = {}
    # Pagination logic
    try:
        page = int(request.args.get('page', 1))
    except Exception:
        page = 1
    per_page = 15
    total = len(nodes)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_nodes = nodes[start:end]
    class Pagination:
        def __init__(self, page, per_page, total):
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = (total + per_page - 1) // per_page
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1
            self.next_num = page + 1
    pagination = Pagination(page, per_page, total)
    return render_template('kobayashi/nodes.html', story=story, nodes=paginated_nodes, pagination=pagination)

@kobayashi_bp.route('/stories/<int:story_id>/nodes/new', methods=['GET', 'POST'])
@login_required
def create_node_route(story_id):
    import json
    story = get_story(story_id)
    if not story:
        flash('Story not found.', 'danger')
        return redirect(url_for('kobayashi.stories'))
    if request.method == 'POST':
        # Collect all fields from form
        import json
        node_data = {
            'id': request.form.get('id'),
            'title': request.form.get('title'),
            'description': request.form.get('description'),
            'is_terminal': bool(request.form.get('is_terminal')),
        }
        # Parse choices
        try:
            choices_json = request.form.get('choices', '{}')
            print('DEBUG: RAW choices from form:', choices_json)
            node_data['choices'] = json.loads(choices_json) if choices_json else {}
        except Exception as e:
            flash(f'Invalid choices data: {e}', 'danger')
            return render_template('kobayashi/node_form.html', story=story, node=node_data)
        # Parse conditions
        try:
            conditions_json = request.form.get('conditions', '[]')
            node_data['conditions'] = json.loads(conditions_json) if conditions_json else []
        except Exception as e:
            flash(f'Invalid conditions data: {e}', 'danger')
            return render_template('kobayashi/node_form.html', story=story, node=node_data)
        # Validate required fields
        if not node_data['id'] or not node_data['title']:
            flash('Node ID and Title are required.', 'danger')
            return render_template('kobayashi/node_form.html', story=story, node=node_data)
        print(node_data)
        create_node(story_id, node_data)
        flash('Node created.', 'success')
        return redirect(url_for('kobayashi.nodes', story_id=story_id))
    return render_template('kobayashi/node_form.html', story=story, node=None)

@kobayashi_bp.route('/nodes/<node_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_node_route(node_id):
    import json
    node = get_node(node_id)
    print("DEBUG: node =", node)
    if not node:
        flash('Node not found.', 'danger')
        return redirect(url_for('kobayashi.stories'))
    story = get_story(node['story_id'])
    # Deserialize content
    node_data = None
    try:
        node_data = json.loads(node['content']) if node and 'content' in node else node
        # Helper to robustly decode JSON (handles double-encoded strings)
        def robust_json_loads(val):
            import json
            tries = 0
            while isinstance(val, str) and tries < 3:
                try:
                    val = json.loads(val)
                except Exception:
                    break
                tries += 1
            return val
        # Ensure choices and conditions are present and correct type (robust)
        if 'choices' in node_data:
            node_data['choices'] = robust_json_loads(node_data['choices'])
        if 'choices' not in node_data or not isinstance(node_data['choices'], dict):
            node_data['choices'] = {}
        if 'conditions' in node_data:
            node_data['conditions'] = robust_json_loads(node_data['conditions'])
        if 'conditions' not in node_data or not isinstance(node_data['conditions'], list):
            node_data['conditions'] = []
    except Exception:
        node_data = node
    if request.method == 'POST':
        import json
        node_data = {
            'id': request.form.get('id'),
            'title': request.form.get('title'),
            'description': request.form.get('description'),
            'is_terminal': bool(request.form.get('is_terminal')),
        }
        # Parse choices
        try:
            choices_json = request.form.get('choices', '{}')
            node_data['choices'] = json.loads(choices_json) if choices_json else {}
            # Ensure flags_required is always an array (for each choice)
            for c in node_data['choices'].values():
                if 'flags_required' in c and not isinstance(c['flags_required'], list):
                    if isinstance(c['flags_required'], str):
                        c['flags_required'] = [f.strip() for f in c['flags_required'].split(',') if f.strip()]
                    else:
                        c['flags_required'] = []
                elif 'flags_required' not in c:
                    c['flags_required'] = []
        except Exception as e:
            flash(f'Invalid choices data: {e}', 'danger')
            return render_template('kobayashi/node_form.html', story=story, node=node_data)
        # Parse conditions
        try:
            conditions_json = request.form.get('conditions', '[]')
            conds = json.loads(conditions_json) if conditions_json else []
            # Convert list of strings to list of dicts [{"flag": ...}]
            if isinstance(conds, list):
                node_data['conditions'] = [{"flag": c} if isinstance(c, str) else c for c in conds]
            else:
                node_data['conditions'] = []
        except Exception as e:
            flash(f'Invalid conditions data: {e}', 'danger')
            return render_template('kobayashi/node_form.html', story=story, node=node_data)

    print("DEBUG: node_data['choices'] =", node_data.get('choices'))
    if request.method == 'POST':
        from models.kobayashi import update_node
        update_node(node_id, node_data)
        flash('Node updated.', 'success')
        return redirect(url_for('kobayashi.nodes', story_id=story['id']))
    return render_template('kobayashi/node_form.html', story=story, node=node_data)

@kobayashi_bp.route('/nodes/<node_id>/delete', methods=['POST'])
@login_required
def delete_node_route(node_id):
    node = get_node(node_id)
    if node:
        story_id = node['story_id']
        delete_node(node_id)
        flash('Node deleted.', 'success')
        return redirect(url_for('kobayashi.nodes', story_id=story_id))
    flash('Node not found.', 'danger')
    return redirect(url_for('kobayashi.stories'))

# --- Simulation ---
@kobayashi_bp.route('/simulate/<int:story_id>', methods=['GET', 'POST'])
@login_required
def simulate(story_id):
    import json
    story = get_story(story_id)
    nodes = get_nodes_for_story(story_id)
    simulation_history = []
    # Track flags set during simulation
    flags_set = []
    # Find the current node id and flags from form or start at first
    current_node_id = None
    if 'current_node_id' in (getattr(request, 'form', {}) or {}):
        current_node_id = request.form.get('current_node_id')
    if 'flags_set' in (getattr(request, 'form', {}) or {}):
        flags_set = json.loads(request.form.get('flags_set', '[]'))
    if not current_node_id:
        current_node = nodes[0] if nodes else None
    else:
        current_node = next((n for n in nodes if n['id'] == current_node_id), nodes[0] if nodes else None)
    # Parse choices
    if current_node:
        choices_raw = current_node.get('choices', '{}')
        for _ in range(2):
            if isinstance(choices_raw, str):
                try:
                    choices_raw = json.loads(choices_raw)
                except Exception:
                    break
        if isinstance(choices_raw, dict):
            current_node['choices'] = choices_raw
        else:
            current_node['choices'] = {}
    # POST: advance to next node if choice made
    if request.method == 'POST' and current_node:
        choice_key = request.form.get('choice')
        choice = current_node['choices'].get(choice_key)
        if choice:
            # Add any flags set by this choice
            flags_to_add = choice.get('flags_set', [])
            for flag in flags_to_add:
                if flag not in flags_set:
                    flags_set.append(flag)
            next_node_id = choice.get('next')
            # Find next node
            next_node = next((n for n in nodes if n['id'] == next_node_id), None)
            if next_node:
                current_node = next_node
                # Parse choices for new node
                choices_raw = current_node.get('choices', '{}')
                for _ in range(2):
                    if isinstance(choices_raw, str):
                        try:
                            choices_raw = json.loads(choices_raw)
                        except Exception:
                            break
                if isinstance(choices_raw, dict):
                    current_node['choices'] = choices_raw
                else:
                    current_node['choices'] = {}
    # Ensure endingtype and endingtext are available for terminal nodes
    endingtype = None
    endingtext = None
    if current_node and current_node.get('is_terminal'):
        endingtype = current_node.get('ending_type') or current_node.get('endingtype')
        endingtext = current_node.get('ending_text') or current_node.get('endingtext')
        current_node['endingtype'] = endingtype
        current_node['endingtext'] = endingtext
    return render_template(
        'kobayashi/simulate.html',
        story=story,
        nodes=nodes,
        current_node=current_node,
        simulation_history=simulation_history,
        flags_set=flags_set
    )

# --- Analytics ---
@kobayashi_bp.route('/analytics')
@login_required
def analytics():
    from models.kobayashi_analytics import (
        get_story_run_stats,
        get_choice_distribution,
        get_user_participation,
        get_analytics_summary,
        get_custom_actions
    )
    
    # Get page and filter parameters
    page = request.args.get('page', 1, type=int)
    run_id = request.args.get('run_id', None)
    
    # Get analytics data from the database
    story_stats = get_story_run_stats()
    choice_stats = get_choice_distribution()
    user_participation = get_user_participation()
    summary = get_analytics_summary()
    custom_actions = get_custom_actions(page=page, per_page=10, run_id=run_id)
    
    return render_template('kobayashi/analytics.html', 
                           story_stats=story_stats,
                           choice_stats=choice_stats,
                           user_participation=user_participation,
                           summary=summary,
                           custom_actions=custom_actions,
                           run_id=run_id)
