import unittest
from stability import Detection,ConfirmedFilter,filter_candidates
<<<<<<< HEAD

SHAPE=(480,640,3)
def d(value=100,confidence=.9,box=(100,100,300,250)):
    return Detection(box,value,confidence)

class ConfirmationTests(unittest.TestCase):
    def test_first_frame_not_counted_or_spoken(self):
        self.assertEqual(ConfirmedFilter().update([d()],SHAPE,.6,0),([],(),None))
    def test_confirm_and_announce_once(self):
        f=ConfirmedFilter();events=[]
        for i in range(12):
            out,values,event=f.update([d()],SHAPE,.6,i*.15)
            if i<3:self.assertEqual(out,[])
            if event:events.append(event)
        self.assertEqual(values,((100,1),));self.assertEqual(len(events),1)
    def test_alternating_classes_never_confirm(self):
        f=ConfirmedFilter()
        for i in range(20):self.assertEqual(f.update([d(100 if i%2 else 500)],SHAPE,.6,i*.15)[0],[])
    def test_brief_false_positive_is_rejected(self):
        f=ConfirmedFilter()
        for i in range(3):self.assertFalse(f.update([d()],SHAPE,.6,i*.15)[0])
        self.assertFalse(f.update([],SHAPE,.6,.5)[0])
    def test_missing_frame_has_no_ghost(self):
        f=ConfirmedFilter()
        for i in range(5):f.update([d()],SHAPE,.6,i*.15)
        self.assertEqual(f.update([],SHAPE,.6,.8),([],(),None))
        self.assertFalse(f.update([d()],SHAPE,.6,.9)[0])
    def test_settings_reset_confirmation(self):
        f=ConfirmedFilter()
        for i in range(5):f.update([d()],SHAPE,.6,i*.15)
        self.assertFalse(f.update([d()],SHAPE,.65,.8)[0])
    def test_classes_conflicting_same_box_are_rejected(self):
        self.assertEqual(filter_candidates([d(),d(500,.86)],SHAPE,.6),[])
    def test_same_class_duplicate_counted_once(self):
        self.assertEqual(len(filter_candidates([d(),d(confidence=.8,box=(101,101,301,251))],SHAPE,.6)),1)
    def test_overlap_and_distinct_notes_remain(self):
        self.assertEqual(len(filter_candidates([d(),d(500,box=(200,150,400,300)),d(box=(400,100,600,250))],SHAPE,.6)),3)
    def test_weak_tiny_invalid_rejected(self):
        self.assertEqual(filter_candidates([d(confidence=.4),d(box=(0,0,2,2)),d(confidence=1.2)],SHAPE,.6),[])
    def test_independent_streams(self):
        a,b=ConfirmedFilter(),ConfirmedFilter()
        for i in range(6):a.update([d()],SHAPE,.6,i*.15)
        self.assertEqual(b.update([d()],SHAPE,.6,1),([],(),None))
    def test_gap_expires(self):
        f=ConfirmedFilter()
        for i in range(5):f.update([d()],SHAPE,.6,i*.15)
        self.assertFalse(f.update([d()],SHAPE,.6,5)[0])

=======
class CameraTests(unittest.TestCase):
    def test_full_frame_false_positive_rejected(self):
        self.assertEqual(filter_candidates([Detection((0,0,640,480),20,.79)],(480,640),.6),[])
    def test_near_full_frame_rejected(self):
        self.assertEqual(filter_candidates([Detection((4,4,636,478),20,.99)],(480,640),.6),[])
    def test_note_immediately_counted_and_spoken(self):
        f=ConfirmedFilter();ds=[Detection((140,80,300,410),50,.8)]
        boxes,counts,event=f.update(ds,(480,640),.6,0)
        self.assertEqual(len(boxes),1);self.assertEqual(counts,((50,1),));self.assertIn('1 ใบ',event)
        self.assertIsNone(f.update(ds,(480,640),.6,.1)[2])
        self.assertEqual(f.update([],(480,640),.6,.2)[0],[])
    def test_false_scene_and_real_note(self):
        ds=[Detection((0,0,640,480),20,.99),Detection((140,80,300,410),50,.8)]
        self.assertEqual([d.value for d in filter_candidates(ds,(480,640),.6)],[50])
    def test_real_overlap_not_removed(self):
        ds=[Detection((50,50,250,200),100,.9),Detection((150,80,350,240),500,.9)]
        self.assertEqual(len(filter_candidates(ds,(480,640),.6)),2)
>>>>>>> c5daf94 (Update detect_server.py)
if __name__=='__main__':unittest.main()
