def test_index_route(client):
    """Test standard index route."""
    response = client.get('/')
    assert response.status_code == 200
    assert b"Azubi Werkzeug Tracker" in response.data

def test_manage_route(client):
    """Test manage route."""
    response = client.get('/manage')
    assert response.status_code == 200
    assert b"Verwaltung" in response.data
