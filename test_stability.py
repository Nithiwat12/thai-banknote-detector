import unittest
from stability import Detection,Stabilizer,AnnouncementGate,deduplicate,signature,speech_text

def d(value=100,box=(0,0,100,100),confidence=.9):
    return Detection(box,value,confidence)

class StabilityTests(unittest.TestCase):
    def test_needs_persistent_observations(self):
        s=Stabilizer()
        for t in (0,.25,.5):self.assertEqual(s.update([d()],t),[])
        self.assertEqual(signature(s.update([d()],.75)),(100,))
    def test_class_flicker_not_announced(self):
        s=Stabilizer()
        for i in range(8):out=s.update([d(100 if i%2 else 500)],i*.25)
        self.assertEqual(out,[])
    def test_wrong_current_class_is_not_stable(self):
        s=Stabilizer()
        for i in range(6):s.update([d()],i*.25)
        self.assertEqual(s.update([d(500)],1.5),[])
    def test_missing_does_not_keep_ghost(self):
        s=Stabilizer()
        for i in range(4):s.update([d()],i*.25)
        self.assertEqual(s.update([],1),[])
        self.assertEqual(s.update([d()],1.25),[])
    def test_long_gap_requires_confirmation_again(self):
        s=Stabilizer()
        for i in range(4):s.update([d()],i*.25)
        self.assertEqual(s.update([d()],5),[])
    def test_multiple_same_class_notes_remain(self):
        s=Stabilizer()
        for i in range(4):out=s.update([d(),d(box=(120,0,220,100))],i*.25)
        self.assertEqual(len(out),2)
        self.assertEqual(signature(out),(100,))
    def test_dedup_preserves_real_overlap_and_other_class(self):
        out=deduplicate([d(),d(box=(1,1,101,101),confidence=.8),d(box=(50,0,150,100)),d(500)])
        self.assertEqual(len(out),3)
    def test_invalid_boxes_filtered(self):
        self.assertEqual(deduplicate([d(box=(0,0,0,0)),d(value=999),d(confidence=float('nan'))]),[])
    def test_gate_once_then_rearm_after_absence(self):
        g=AnnouncementGate()
        self.assertIsNone(g.update((100,),0))
        self.assertEqual(g.update((100,),1),speech_text((100,)))
        self.assertIsNone(g.update((100,),8))
        g.update((),9);g.update((),12)
        g.update((100,),13)
        self.assertIsNotNone(g.update((100,),14))
    def test_cooldown_keeps_latest_not_stale(self):
        g=AnnouncementGate();g.update((100,),0);g.update((100,),1)
        g.update((500,),2);self.assertIsNone(g.update((500,),3))
        g.update((20,),4)
        self.assertEqual(g.update((20,),5),speech_text((20,)))


class CountTests(unittest.TestCase):
    def test_counts_and_immediate_announcement(self):
        from stability import count_signature,count_speech_text
        values=count_signature(deduplicate([d(),d(box=(120,0,220,100)),d(20,box=(240,0,340,100)),d(box=(1,1,101,101),confidence=.8)]))
        self.assertEqual(values,((20,1),(100,2)))
        g=AnnouncementGate(cooldown=0,hold=0,formatter=count_speech_text)
        self.assertEqual(g.update(values,0),'พบธนบัตร ยี่สิบบาท 1 ใบ และ หนึ่งร้อยบาท 2 ใบ')
        self.assertIsNone(g.update(values,.1))
        self.assertEqual(g.update(((100,3),),.2),'พบธนบัตร หนึ่งร้อยบาท 3 ใบ')

if __name__=='__main__':unittest.main()
