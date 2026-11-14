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


def test_tick_faults_replay_real_circuit_without_future_detectors():
    model = lab()
    layout = model.layout()
    assert 'ticks' in layout, 'circuit TICK replay is missing'
    assert len(layout['ticks']) == str(model.clean).count('TICK') + 1
    faults = [{'tick': 9, 'qubit': 10, 'pauli': 'X'},
              {'tick': 16, 'qubit': 10, 'pauli': 'Z'}]
    result = model.simulate_faults(faults)
    assert model._sample(stim.Circuit(result['injected_circuit'])) == (result['syndrome'], result['observable'])
    assert len(result['trace']) == len(layout['ticks'])
    assert not result['trace'][8]['faults']
    assert result['trace'][9]['faults'] == faults[:1]
    for tick, frame in enumerate(result['trace']):
        assert all(layout['detectors'][i]['available_tick'] <= tick for i in frame['detector_indices'])
    assert result['trace'][-1]['detector_indices'] == result['detector_indices']
    assert result['source'] == 'Simulated'
    assert result['host_frame'] == result['prediction']


def test_fpga_prediction_drives_host_frame_and_failure_never_falls_back():
    from qec.surface.web import Lab
    calls = []
    def board(syndrome):
        calls.append(syndrome)
        return {'prediction': 1, 'cycles': 1234, 'tx_hex': 'c3', 'rx_hex': '3c'}
    model = Lab(decoder=board)
    result = model.simulate_faults([])
    assert calls == [0]
    assert result['source'] == 'FPGA'
    assert result['prediction'] == result['host_frame'] == 1
    assert result['logical_success'] is False
    assert result['hardware']['cycles'] == 1234
    assert result['reference_prediction'] == 0
    def broken(syndrome):
        raise IOError('timeout')
    with pytest.raises(IOError, match='timeout'):
        Lab(decoder=broken).simulate_faults([])


def test_tick_correction_is_independently_replayed_and_frames_propagate():
    model = lab()
    fault = {'tick': 8, 'qubit': 10, 'pauli': 'X'}
    result = model.simulate_faults([fault])
    assert result['trace'][7]['pauli_frame'] == {}
    assert result['trace'][8]['pauli_frame']['10'] == 'X'
    assert result['correction'] is not None
    assert model._sample(stim.Circuit(result['corrected_circuit'])) == (0, result['observable'] ^ result['prediction'])
    assert result['residual_syndrome'] == 0
    assert result['residual_observable'] == result['observable'] ^ result['host_frame']
    late = model.simulate_faults([dict(fault, tick=21)])
    assert late['syndrome'] != result['syndrome']
    for tick in range(len(model.layout()['ticks'])):
        r = model.simulate_faults([dict(fault, tick=tick)])
        assert model._sample(stim.Circuit(r['injected_circuit'])) == (r['syndrome'], r['observable'])
        if r['correction'] is not None:
            assert r['residual_syndrome'] == 0
    for faults in [None, {}, [{'tick': -1, 'qubit': 10, 'pauli': 'X'}],
                   [{'tick': True, 'qubit': 10, 'pauli': 'X'}],
                   [{'tick': 22, 'qubit': 10, 'pauli': 'X'}],
                   [{'tick': 8, 'qubit': 2, 'pauli': 'X'}], [fault] * 65]:
        with pytest.raises(ValueError):
            model.simulate_faults(faults)


def test_serial_transport_real_pty_framing_failure_and_recovery():
    import os
    import pty
    from functools import reduce
    from operator import xor
    from qec.surface import web, host
    assert hasattr(web, 'SerialDecoder'), 'serial transport is missing'
    master, slave = pty.openpty()
    endpoint = web.SerialDecoder(os.ttyname(slave), timeout=.15)
    received = []
    def firmware():
        for i in range(3):
            tx = b''
            while len(tx) < 7:
                tx += os.read(master, 7 - len(tx))
            received.append(tx)
            packet = bytes([0x3c, tx[1], 0, 1]) + (3456).to_bytes(4, 'little')
            packet += bytes([reduce(xor, packet) ^ (1 if i == 0 else 0)])
            os.write(master, packet[:3])
            os.write(master, packet[3:])
    thread = threading.Thread(target=firmware, daemon=True)
    thread.start()
    try:
        with pytest.raises(IOError):
            endpoint(17)
        result = endpoint(23)
        assert result['prediction'] == 1 and result['cycles'] == 3456
        assert bytes.fromhex(result['tx_hex']) == host.request(1, 23)
        assert host.parse(bytes.fromhex(result['rx_hex']), 1) == (1, 3456)
        assert endpoint(0)['cycles'] == 3456
        thread.join(1)
        assert received == [host.request(i, s) for i, s in enumerate([17, 23, 0])]
        with pytest.raises(IOError, match='reply'):
            endpoint(0)
    finally:
        os.close(master)
        os.close(slave)


def test_http_tick_faults_and_hardware_failure_recovery():
    from qec.surface.web import make_server
    fail = [True]
    def board(syndrome):
        if fail[0]:
            raise IOError('board timeout')
        return {'prediction': 0, 'cycles': 3}
    server = make_server(port=0, decoder=board)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = 'http://127.0.0.1:' + str(server.server_port)
    try:
        req = urllib.request.Request(root + '/api/simulate', data=b'{"faults":[]}')
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 503
        assert 'board timeout' in exc.value.read().decode()
        fail[0] = False
        with urllib.request.urlopen(req) as response:
            assert json.load(response)['source'] == 'FPGA'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_cli_accepts_explicit_serial_source():
    import subprocess
    from qec.surface.web import Lab
    assert Lab().layout()['source'] == 'Simulated'
    assert Lab(decoder=lambda s: None).layout()['source'] == 'FPGA'
    completed = subprocess.run(['qec/.venv/bin/python', '-m', 'qec.surface.web', '--help'],
                               capture_output=True, text=True)
    assert '--serial-port' in completed.stdout


def test_serial_port_contention_is_explicit_and_lock_timeout_is_bounded():
    import os
    import pty
    import serial
    import time
    from qec.surface.web import SerialDecoder
    master, slave = pty.openpty()
    port = os.ttyname(slave)
    endpoint = SerialDecoder(port, timeout=.05)
    try:
        with serial.Serial(port, 115200, exclusive=True):
            with pytest.raises(IOError):
                endpoint(0)
        endpoint.lock.acquire()
        start = time.monotonic()
        try:
            with pytest.raises(IOError, match='busy'):
                endpoint(0)
            assert time.monotonic() - start < .5
        finally:
            endpoint.lock.release()
        # The previous failures did not leave the endpoint locked.
        with pytest.raises(IOError, match='reply'):
            endpoint(0)
    finally:
        os.close(master)
        os.close(slave)


def test_multitime_replay_and_zero_syndrome_logical_chain():
    model = lab()
    result = model.simulate_faults([dict(tick=8, qubit=q, pauli='X') for q in [1, 8, 15]])
    assert result['syndrome'] == 0 and result['observable'] == 1
    assert result['logical_success'] is False
    rng = random.Random(2)
    qubits = [q['id'] for q in model.layout()['data']]
    for _ in range(40):
        faults = [dict(tick=rng.randrange(22), qubit=rng.choice(qubits), pauli=rng.choice('XYZ'))
                  for _ in range(rng.randrange(1, 8))]
        result = model.simulate_faults(faults)
        expected_s = expected_o = 0
        for fault in faults:
            s, o = model._sample(model._fault_circuit([fault]))
            expected_s ^= s
            expected_o ^= o
        assert (result['syndrome'], result['observable']) == (expected_s, expected_o)
        if result['correction'] is not None:
            assert result['residual_syndrome'] == 0
            assert result['residual_observable'] == expected_o ^ result['prediction']
    assert model._basis.cache_info().currsize <= 8
    assert model._signature.cache_info().currsize <= 512


def test_configured_hardware_cannot_silently_become_simulated():
    from qec.surface.web import Lab
    for invalid in [None, {}, {'prediction': 2, 'cycles': 1}, {'prediction': 0, 'cycles': 0}]:
        with pytest.raises(IOError, match='FPGA'):
            Lab(decoder=lambda s: invalid).simulate_faults([])


def test_layout_is_derived_from_stim():
    model = lab().layout()
    assert model['injection'] == 'Before selected tick operations'
    assert len(model['data']) == 9
    assert len(model['checks']) == 8
    assert len(model['detectors']) == 24
    assert next(q for q in model['data'] if q['id'] == 1)['coords'] == [1, 1]
    assert next(q for q in model['checks'] if q['id'] == 9)['support'] == [1, 3, 8, 10]
    assert next(q for q in model['checks'] if q['id'] == 9)['basis'] == 'Z'
    assert {d['coords'][2] for d in model['detectors']} == {0, 1, 2, 3}
