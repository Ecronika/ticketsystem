from app import app, db, Azubi, Werkzeug
from flask import template_rendered
import sys
import contextlib

def verify_routes():
    print("Verifying Routes...")
    rules = [str(p) for p in app.url_map.iter_rules()]
    expected = ['/', '/check/<azubi_id>', '/submit_check', '/history', '/static/<path:filename>']
    
    missing = []
    for exp in expected:
        found = False
        for rule in rules:
            if exp in rule: # loose matching for parameters
                found = True
                break
        if not found:
            missing.append(exp)
            
    if missing:
        print(f"FAILED: Missing routes: {missing}")
        sys.exit(1)
    print("Routes OK")

def verify_templates():
    print("Verifying Templates...")
    with app.test_request_context('/'):
        try:
            # Test Index
            app.jinja_env.get_template('index.html').render(azubis=[])
            print("index.html OK")
            
            # Test Check
            mock_azubi = Azubi(name="Test")
            mock_azubi.id = 1
            mock_werkzeuge = [Werkzeug(name="Hammer", id=1)]
            app.jinja_env.get_template('check.html').render(
                azubi=mock_azubi, 
                werkzeuge=mock_werkzeuge, 
                current_date="01.01.2024"
            )
            print("check.html OK")
            
            # Test Base (implicitly tested above, but being explicit)
            app.jinja_env.get_template('base.html').render()
            print("base.html OK")
            
        except Exception as e:
            print(f"FAILED: Template error: {e}")
            sys.exit(1)

if __name__ == '__main__':
    verify_routes()
    verify_templates()
    print("All Verifications Passed.")
