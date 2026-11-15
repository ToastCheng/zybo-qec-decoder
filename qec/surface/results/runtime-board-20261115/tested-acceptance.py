from pathlib import Path
import json,sys,random,stim
root=Path('/home/toastcheng/dev/zybo-qec-decoder')
sys.path.insert(0,str(root))
from qec.surface.runtime_circuit import compile_circuit
from qec.surface.runtime_host import RuntimeSerialDecoder
from qec.surface.decoder import decode
out=root/'build/runtime-board-multigraph'
out.mkdir(exist_ok=False)
examples=[(p.stem,p.read_text()) for p in sorted((root/'qec/examples/runtime').glob('*.stim'))]
examples.append(('unlisted-bit31','R 0 1 2\nH 2\nTICK\nH 2\nX_ERROR(1) 2\nM 2\nDETECTOR rec[-1]\nOBSERVABLE_INCLUDE(31) rec[-1]\n'))
for d,b,r in [(3,'z',3),(3,'x',5),(5,'z',3)]:
    c=stim.Circuit.generated('surface_code:rotated_memory_'+b,distance=d,rounds=r,after_clifford_depolarization=.001,before_round_data_depolarization=.001,before_measure_flip_probability=.001,after_reset_flip_probability=.001)
    examples.append((f'memory-d{d}-{b}-r{r}',str(c)))
summaries=[]
with RuntimeSerialDecoder('/dev/ttyUSB1',timeout=2) as board:
    initial=board.identity()
    (out/'initial-identity.json').write_text(json.dumps(initial.words))
    for name,text in examples:
        bundle=compile_circuit(text)
        (out/(name+'.json')).write_text(json.dumps(bundle,indent=2))
        c=stim.Circuit(bundle['circuit'])
        identity=board.load_graph(c.num_detectors,bundle['edges'],c.num_observables)
        ds,os=c.compile_detector_sampler(seed=123).sample(128,separate_observables=True)
        rows=[]
        for d,o in zip(ds,os):
            syndrome=sum(int(x)<<i for i,x in enumerate(d))
            truth=sum(int(x)<<i for i,x in enumerate(o))
            ref=decode(c.num_detectors,bundle['edges'],syndrome)
            reply=board.decode(syndrome)
            assert not reply.decode_error and reply.cycles>0
            assert reply.prediction==ref['prediction'] and not ref['error'],(name,syndrome,reply,ref)
            rows.append(dict(syndrome=syndrome,truth=truth,prediction=reply.prediction,cycles=reply.cycles))
        rng=random.Random(15)
        diagnostic=[0]+[1<<i for i in range(c.num_detectors)]+[(1<<c.num_detectors)-1]+[rng.getrandbits(c.num_detectors) for _ in range(16)]
        for syndrome in diagnostic:
            ref=decode(c.num_detectors,bundle['edges'],syndrome)
            reply=board.decode(syndrome)
            assert reply.prediction==ref['prediction'] and not ref['error']
        (out/(name+'-shots.json')).write_text(json.dumps(rows,indent=2))
        result=dict(name=name,counts=bundle['counts'],generation=identity.generation,shots=len(rows),diagnostic_windows=len(diagnostic),reference_mismatches=0,logical_failures=sum(r['prediction']!=r['truth'] for r in rows),min_cycles=min(r['cycles'] for r in rows),max_cycles=max(r['cycles'] for r in rows))
        summaries.append(result)
        print(json.dumps(result),flush=True)
    board.save_archive(out/'wire.json')
    final=board.identity()
    assert final.generation==initial.generation+len(examples)
    (out/'summary.json').write_text(json.dumps(dict(source='FPGA',reprogrammed_between_graphs=False,initial_generation=initial.generation,final_generation=final.generation,circuits=summaries),indent=2)+'\n')
print('PASS all physical graph reloads and sampled/diagnostic decodes')
