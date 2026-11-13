"""Software-only interactive lab contracts; no hardware required."""
import importlib.util
import json
import random
import threading
import urllib.error
import urllib.request

import pytest
import stim

from qec.surface.decoder import decode


def test_injection_replays_real_stim_and_decoder_correction():
    model = lab()
    assert hasattr(model, 'simulate'), 'simulation endpoint is missing'
    clean = model.simulate({})
    assert clean['syndrome'] == clean['observable'] == clean['residual_syndrome'] == 0
    for pauli in 'XYZ':
        for q in [1, 3, 5, 8, 10, 12, 15, 17, 19]:
            result = model.simulate({str(q): pauli})
            circuit = stim.Circuit(result['injected_circuit'])
            bits, obs = circuit.compile_detector_sampler(seed=42).sample(1, separate_observables=True)
            assert result['syndrome'] == sum(int(b) << i for i, b in enumerate(bits[0]))
            assert result['observable'] == int(obs[0, 0])
            expected = decode(24, model.config['edges'], result['syndrome'])
            assert result['correction_edges'] == expected['correction_edges']
            assert result['prediction'] == expected['prediction']
            assert result['graph_residual'] == 0
            assert result['residual_syndrome'] == 0
            assert result['residual_observable'] == (result['observable'] ^ result['prediction'])
            assert result['logical_success'] == (result['residual_observable'] == 0)
            if pauli == 'Z':
                assert result['syndrome'] != 0  # X checks see phase errors in intermediate rounds


def test_input_bounds_and_logical_failure_are_explicit():
    model = lab()
    for bad in [None, [], {'2': 'X'}, {'1': 'H'}, {'01': 'X'}, {'1': 1}, {'1': 'x'}]:
        with pytest.raises(ValueError):
            model.simulate(bad)
    # A complete logical X has no detection events but flips the Z observable.
    result = model.simulate({'1': 'X', '8': 'X', '15': 'X'})
    assert result['syndrome'] == result['graph_residual'] == result['residual_syndrome'] == 0
    assert result['observable'] == result['residual_observable'] == 1
    assert result['logical_success'] is False
    assert model.simulate({})['logical_success'] is True


def test_http_api_rejects_bad_requests_and_recovers():
    import qec.surface.web as web
    assert hasattr(web, 'make_server'), 'HTTP server is missing'
    server = web.make_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = 'http://127.0.0.1:' + str(server.server_port)
    try:
        with urllib.request.urlopen(root + '/api/layout') as response:
            assert len(json.load(response)['data']) == 9
        for body, status in [(b'{bad', 400), (b'[]', 400), (b'{"errors":{"2":"X"}}', 400),
                             (b'x' * 4097, 413)]:
            req = urllib.request.Request(root + '/api/simulate', data=body,
                                         headers={'Content-Type': 'application/json'})
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(req)
            assert error.value.code == status
        req = urllib.request.Request(root + '/api/simulate', data=b'{"errors":{"10":"X"}}',
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            assert json.load(response)['residual_syndrome'] == 0
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(root + '/../../README.md')
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_multiqubit_faults_and_exported_replays_match_stim():
    model = lab()
    data = [str(q['id']) for q in model.layout()['data']]
    effects = {(q, p): model._sample(model._circuit({q: p})) for q in data for p in 'XYZ'}
    frames = []
    for p in 'XZ':
        frames.extend({q: p for i, q in enumerate(data) if mask >> i & 1} for mask in range(512))
    rng = random.Random(20261114)
    frames.extend({q: p for q in data if (p := rng.choice('IXYZ')) != 'I'} for _ in range(128))
    failures = 0
    for frame in frames:
        result = model.simulate(frame)
        syndrome = observable = 0
        for q, p in frame.items():
            s, o = effects[q, p]
            syndrome ^= s
            observable ^= o
        assert (result['syndrome'], result['observable']) == (syndrome, observable)
        assert result['correction'] is not None
        assert result['graph_residual'] == result['residual_syndrome'] == 0
        replay = stim.Circuit(result['corrected_circuit'])
        bits, obs = replay.compile_detector_sampler(seed=999).sample(1, separate_observables=True)
        assert not bits.any()
        assert int(obs[0, 0]) == result['residual_observable'] == observable ^ result['prediction']
        failures += not result['logical_success']
    assert failures > 0


def test_http_assets_are_local_and_cross_origin_writes_rejected():
    from qec.surface.web import make_server
    server = make_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = 'http://127.0.0.1:' + str(server.server_port)
    try:
        for asset, mime in [('/', 'text/html'), ('/app.js', 'text/javascript'), ('/style.css', 'text/css')]:
            with urllib.request.urlopen(root + asset) as response:
                assert response.headers['Content-Type'].startswith(mime)
                assert response.headers['Cache-Control'] == 'no-store'
                assert len(response.read()) > 100
        req = urllib.request.Request(root + '/api/simulate', data=b'{"errors":{}}',
                                     headers={'Origin': 'https://untrusted.example'})
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(req)
        assert error.value.code == 403
        req = urllib.request.Request(root + '/api/simulate', data=b'{"errors":{}}')
        with urllib.request.urlopen(req) as response:
            assert json.load(response)['logical_success'] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def lab():
    assert importlib.util.find_spec('qec.surface.web') is not None, 'interactive lab is missing'
    from qec.surface.web import Lab
    return Lab()


def test_layout_is_derived_from_stim():
    model = lab().layout()
    assert len(model['data']) == 9
    assert len(model['checks']) == 8
    assert len(model['detectors']) == 24
    assert next(q for q in model['data'] if q['id'] == 1)['coords'] == [1, 1]
    assert next(q for q in model['checks'] if q['id'] == 9)['support'] == [1, 3, 8, 10]
    assert next(q for q in model['checks'] if q['id'] == 9)['basis'] == 'Z'
    assert {d['coords'][2] for d in model['detectors']} == {0, 1, 2, 3}
