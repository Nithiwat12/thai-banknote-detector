import unittest
from stability import Detection,ConfirmedFilter,filter_candidates

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

if __name__=='__main__':unittest.main()
