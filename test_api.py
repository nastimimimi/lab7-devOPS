import pytest
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app, InputData, GeneticScheduler

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c

def test_health(client):
    r = client.get('/health')
    assert r.status_code == 200
    assert json.loads(r.data)['status'] == 'ok'

def test_index(client):
    r = client.get('/')
    assert r.status_code == 200

def test_calculate_success(client):
    r = client.post('/calculate',
                    data=json.dumps({'max_generations': 5, 'pop_size': 10}),
                    content_type='application/json')
    assert r.status_code == 200
    assert json.loads(r.data)['status'] == 'success'

def test_calculate_fields(client):
    r = client.post('/calculate',
                    data=json.dumps({'max_generations': 5, 'pop_size': 10}),
                    content_type='application/json')
    result = json.loads(r.data)['result']
    for f in ('conflicts', 'gaps', 'final_score', 'schedule_preview'):
        assert f in result

def test_conflicts_non_negative(client):
    r = client.post('/calculate',
                    data=json.dumps({'max_generations': 3, 'pop_size': 5}),
                    content_type='application/json')
    assert json.loads(r.data)['result']['conflicts'] >= 0

def test_input_data():
    d = InputData(5, 10, 4, 3)
    assert len(d.teachers) == 5
    assert len(d.courses)  == 10

def test_scheduler():
    d         = InputData(3, 5, 3, 2)
    scheduler = GeneticScheduler(d, pop_size=5, max_generations=3)
    result    = scheduler.run()
    assert len(result) == 5
    assert scheduler._count_conflicts(result) >= 0
