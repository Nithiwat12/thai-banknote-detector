import time
import unittest
import numpy as np
from media import InferenceWorker
from stability import Detection

class Source:
    def __init__(self):self.seq=0;self.closed=False
    def read(self):
        self.seq+=1
        return self.seq,np.zeros((8,8,3),dtype=np.uint8),None
    def close(self):self.closed=True

class WorkerTests(unittest.TestCase):
    def test_slow_inference_confirms_and_read_is_nonblocking(self):
        source=Source()
        def infer(frame,conf):
            time.sleep(.85)
            return frame,[Detection((0,0,6,6),100,.9)],1.,''
        worker=InferenceWorker(source,infer,.4)
        try:
            start=time.monotonic();worker.read()
            self.assertLess(time.monotonic()-start,.1)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                packet,error=worker.read()
                if packet and packet[3]:break
                time.sleep(.02)
            self.assertEqual(packet[3][0].value,100);self.assertIsNone(error)
        finally:
            worker.close();worker.thread.join(2)
        self.assertTrue(source.closed)
    def test_speech_on_first_detection_without_temporal_confirmation(self):
        source=Source()
        def infer(frame,conf):
            return frame,[Detection((0,0,6,6),100,.9)],30.,''
        worker=InferenceWorker(source,infer,.4)
        try:
            deadline=time.monotonic()+1
            while time.monotonic()<deadline:
                packet,error=worker.read()
                if packet:break
                time.sleep(.001)
            self.assertEqual(packet[0],1)
            self.assertEqual(packet[3],[])
            self.assertEqual(packet[6],((100,1),))
            self.assertEqual(packet[7],'พบธนบัตร หนึ่งร้อยบาท 1 ใบ')
        finally:worker.close()
    def test_confidence_changes_without_restart(self):
        source=Source();seen=[]
        def infer(frame,conf):
            seen.append(conf);return frame,[],30.,''
        worker=InferenceWorker(source,infer,.4)
        try:
            time.sleep(.04);worker.confidence=.7;time.sleep(.04)
            self.assertIn(.4,seen);self.assertIn(.7,seen)
        finally:worker.close()

if __name__=='__main__':unittest.main()
