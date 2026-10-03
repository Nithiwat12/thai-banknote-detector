"""Temporal filtering independent of UI and ML libraries."""
from collections import Counter, deque
from dataclasses import dataclass, field
import math

DENOMINATIONS = (20, 50, 100, 500, 1000)

@dataclass
class Detection:
    box: tuple
    value: int
    confidence: float

def iou(a, b):
    w = max(0., min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0., min(a[3], b[3]) - max(a[1], b[1]))
    area = lambda x: max(0., x[2]-x[0]) * max(0., x[3]-x[1])
    union = area(a) + area(b) - w*h
    return w*h/union if union > 0 else 0.

def deduplicate(detections, threshold=.85):
    """Conservative same-class near-identical suppression, not containment."""
    kept = []
    for d in sorted(detections, key=lambda d: d.confidence, reverse=True):
        if d.value not in DENOMINATIONS or not all(math.isfinite(x) for x in (*d.box,d.confidence)):
            continue
        if d.box[2] <= d.box[0] or d.box[3] <= d.box[1]:
            continue
        if not any(d.value == k.value and iou(d.box,k.box) >= threshold for k in kept):
            kept.append(d)
    return kept

@dataclass
class Track:
    id: int
    box: tuple
    first: float
    last: float
    votes: deque = field(default_factory=lambda: deque(maxlen=6))
    current: Detection | None = None

class Stabilizer:
    def __init__(self, min_hits=4, min_seconds=.6, max_gap=.8):
        self.tracks = []
        self.next_id = 1
        self.min_hits, self.min_seconds, self.max_gap = min_hits, min_seconds, max_gap

    def update(self, detections, now):
        self.tracks = [t for t in self.tracks if now-t.last <= self.max_gap]
        for t in self.tracks:
            t.current = None
        # Match independent of class so a brief denomination flip cannot create
        # a second stable track on the same box.
        pairs = sorted(((iou(t.box,d.box), ti,di) for ti,t in enumerate(self.tracks)
                        for di,d in enumerate(detections)), reverse=True)
        used_t,used_d = set(),set()
        for score,ti,di in pairs:
            if score < .35 or ti in used_t or di in used_d:
                continue
            t,d = self.tracks[ti],detections[di]
            t.box = tuple(.65*a+.35*b for a,b in zip(t.box,d.box))
            t.last,t.current = now,d
            t.votes.append(d.value)
            used_t.add(ti);used_d.add(di)
        for di,d in enumerate(detections):
            if di not in used_d:
                t=Track(self.next_id,d.box,now,now,current=d)
                t.votes.append(d.value); self.tracks.append(t); self.next_id+=1
        stable=[]
        for t in self.tracks:
            if t.current is None:
                # Missing observations break confirmation, but preserve a short
                # spatial association. No ghost boxes or stale announcements.
                t.votes.clear();t.first=now
                continue
            value,hits=Counter(t.votes).most_common(1)[0]
            if (hits >= self.min_hits and hits/len(t.votes) >= .75
                    and now-t.first >= self.min_seconds and t.current.value == value):
                stable.append(Detection(t.box,value,t.current.confidence))
        return stable

def signature(detections):
    # Announce denominations, NOT number of notes or total money. Partial
    # duplicate boxes cannot make the application announce a wrong total.
    return tuple(sorted({d.value for d in detections}))

def speech_text(values):
    names={20:'ยี่สิบ',50:'ห้าสิบ',100:'หนึ่งร้อย',500:'ห้าร้อย',1000:'หนึ่งพัน'}
    return 'พบธนบัตร ' + ' และ '.join(names[v]+'บาท' for v in values) if values else ''

class AnnouncementGate:
    def __init__(self, cooldown=4., hold=.7, clear_after=2., formatter=speech_text):
        self.formatter=formatter
        self.cooldown,self.hold,self.clear_after=cooldown,hold,clear_after
        self.candidate=(); self.since=0.; self.last=(); self.last_time=-math.inf

    def update(self, values, now):
        if values != self.candidate:
            self.candidate=values; self.since=now
        if not values:
            if now-self.since >= self.clear_after:
                self.last=()
            return None
        if (values != self.last and now-self.since >= self.hold
                and now-self.last_time >= self.cooldown):
            self.last,self.last_time=values,now
            return self.formatter(values)
        return None


def count_signature(detections):
    return tuple(sorted(Counter(d.value for d in detections).items()))

def count_speech_text(values):
    names={20:'ยี่สิบ',50:'ห้าสิบ',100:'หนึ่งร้อย',500:'ห้าร้อย',1000:'หนึ่งพัน'}
    return 'พบธนบัตร ' + ' และ '.join(f'{names[value]}บาท {count} ใบ' for value,count in values) if values else ''


def filter_candidates(detections, shape, confidence):
    """Reject invalid/tiny boxes and ambiguous near-identical class predictions.

    Ordinary overlapping notes are retained; containment alone is not a duplicate.
    """
    h,w=shape[:2]
    valid=[]
    for d in deduplicate(detections,threshold=.80):
        if d.confidence < confidence or d.confidence > 1:continue
        x1,y1,x2,y2=d.box
        box=(max(0.,x1),max(0.,y1),min(float(w),x2),min(float(h),y2))
        bw,bh=box[2]-box[0],box[3]-box[1]
        if bw<=0 or bh<=0 or bw*bh/(w*h)<.003 or min(bw/w,bh/h)<.015:continue
<<<<<<< HEAD
=======
        # Reject scene-sized boxes, including the near-full-frame 20 THB false
        # detection reported by the user. A note held too close can also fail.
        if bw*bh/(w*h)>=.85 or (bw/w>=.95 and bh/h>=.90):continue
>>>>>>> c5daf94 (Update detect_server.py)
        valid.append(Detection(box,d.value,d.confidence))
    rejected=set()
    for i,a in enumerate(valid):
        for j in range(i+1,len(valid)):
            b=valid[j]
            if a.value!=b.value and iou(a.box,b.box)>=.85:
                if abs(a.confidence-b.confidence)<.12:rejected.update((i,j))
                else:rejected.add(i if a.confidence<b.confidence else j)
    return [d for i,d in enumerate(valid) if i not in rejected]


class ConfirmedFilter:
<<<<<<< HEAD
    """Per-stream temporal state; never return missing or unconfirmed objects."""
    def __init__(self):
        self.settings=None
        self.tracker=Stabilizer(min_hits=4,min_seconds=.35,max_gap=3.)
        self.gate=AnnouncementGate(cooldown=1.5,hold=.25,formatter=count_speech_text)
=======
    """Legacy import name; spatial filtering immediately, no frame confirmation."""
    def __init__(self):
        self.settings=None
        self.gate=AnnouncementGate(cooldown=0.,hold=0.,formatter=count_speech_text)
>>>>>>> c5daf94 (Update detect_server.py)

    def update(self,detections,shape,confidence,now):
        settings=(tuple(shape[:2]),float(confidence))
        if settings!=self.settings:
            self.__init__();self.settings=settings
        candidates=filter_candidates(detections,shape,confidence)
<<<<<<< HEAD
        stable=self.tracker.update(candidates,now)
        # Require the most recent three observed classes to agree as well as
        # the four-vote/75% rule, preventing immediate switches between classes.
        eligible=[t for t in self.tracker.tracks if t.current is not None
                  and len(t.votes)>=3 and len(set(list(t.votes)[-3:]))==1]
        stable=[d for d in stable if any(t.box==d.box and t.current.value==d.value for t in eligible)]
        values=count_signature(stable)
        return stable,values,self.gate.update(values,now)
=======
        values=count_signature(candidates)
        return candidates,values,self.gate.update(values,now)
>>>>>>> c5daf94 (Update detect_server.py)
