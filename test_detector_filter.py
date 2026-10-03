import unittest
import numpy as np
from stability import Detection,ConfirmedFilter
from detect_server import build_response


class DetectorFilterTests(unittest.TestCase):
    def test_response_only_contains_confirmed_objects(self):
        frame=np.zeros((480,640,3),np.uint8)
        detector=lambda f,c:([Detection((100,100,300,250),100,.9)],30.,'')
        state=ConfirmedFilter()
        for i in range(6):
            result=build_response(frame,detector,.6,state,now=i*.15)
            if i<3:self.assertEqual(result['boxes'],[]);self.assertEqual(result['text'],'')
        self.assertEqual(len(result['boxes']),1)
        self.assertIn('1 ใบ',result['text'])
        other=build_response(frame,detector,.6,ConfirmedFilter(),now=1)
        self.assertEqual(other['boxes'],[])
    def test_missing_clears_boxes_and_text(self):
        frame=np.zeros((480,640,3),np.uint8);state=ConfirmedFilter()
        detector=lambda f,c:([Detection((100,100,300,250),100,.9)],30.,'')
        for i in range(6):build_response(frame,detector,.6,state,now=i*.15)
        result=build_response(frame,lambda f,c:([],30.,''),.6,state,now=1)
        self.assertEqual(result['text'],'');self.assertEqual(result['boxes'],[])


class ResponseTests(unittest.TestCase):
    def test_immediate_camera_response(self):
        detector=lambda f,c:([Detection((0,0,640,480),20,.79),Detection((140,80,300,410),50,.8)],30.,'')
        result=build_response(np.zeros((480,640,3),np.uint8),detector,.6,ConfirmedFilter(),now=0)
        self.assertEqual(len(result['boxes']),1);self.assertIn('ห้าสิบ',result['text'])

if __name__=='__main__':unittest.main()
