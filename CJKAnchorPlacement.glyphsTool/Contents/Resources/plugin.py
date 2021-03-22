# encoding: utf-8

from GlyphsApp import *
from GlyphsApp.plugins import *
from AppKit import NSGraphicsContext, NSColor, NSMakeRect, NSInsetRect, NSMakePoint, NSAlternateKeyMask, NSBeep, NSNumberFormatter, NSValueTransformer
from Foundation import NSNotFound, NSNumber, NSMutableDictionary
import math
import collections
import contextlib

@contextlib.contextmanager
def currentGraphicsContext(context=None):
    context = context or NSGraphicsContext.currentContext()
    context.saveGraphicsState()
    try:
        yield context
    finally:
        context.restoreGraphicsState()

def upsert_anchor(font, master, layer, name, value, vertical=False):
    anchor = layer.anchors[name]
    if not anchor:
        anchor = GSAnchor(name, NSPoint(0.0, 0.0))
        layer.anchors.append(anchor)
    if vertical:
        anchor.position = NSPoint(layer.width / 2.0, value)
    else:
        anchor.position = NSPoint(value, font.upm / 2.0 + master.descender)

def delete_anchor(font, master, layer, name):
    anchor_to_be_deleted = layer.anchors[name]
    if anchor_to_be_deleted:
        del layer.anchors[name]
 
def arrange_anchors(font, master, layer):
    if layer:
        center_x = layer.width / 2.0
        center_y = font.upm / 2.0 + master.descender
        
        lsb_anchor = layer.anchors['LSB'] if layer.anchors else None
        rsb_anchor = layer.anchors['RSB'] if layer.anchors else None
        tsb_anchor = layer.anchors['TSB'] if layer.anchors else None
        bsb_anchor = layer.anchors['BSB'] if layer.anchors else None
        
        for anchor in [lsb_anchor, rsb_anchor]:
            if anchor:
                position = NSPoint(anchor.position.x, center_y)
                if position != anchor.position:
                    anchor.position = position
        for anchor in [tsb_anchor, bsb_anchor]:
            if anchor:
                position = NSPoint(center_x, anchor.position.y)
                if position != anchor.position:
                    anchor.position = position

def apply_values_for_anchors(font, master, layer, lsb_value, rsb_value, tsb_value, bsb_value):
    if layer:
        vert_width = layer.vertWidth() if callable(layer.vertWidth) else layer.vertWidth
        if vert_width is None:
            vert_width = master.ascender - master.descender
        ascender, descender = (master.ascender, master.ascender - vert_width)

        if lsb_value is not None:
            upsert_anchor(font, master, layer, 'LSB', lsb_value, vertical=False)
        else:
            delete_anchor(font, master, layer, 'LSB')   
        if rsb_value is not None:
            upsert_anchor(font, master, layer, 'RSB', layer.width - rsb_value, vertical=False)
        else:
            delete_anchor(font, master, layer, 'RSB')
        if tsb_value is not None:
            upsert_anchor(font, master, layer, 'TSB', ascender - tsb_value, vertical=True)
        else:
            delete_anchor(font, master, layer, 'TSB')
        if bsb_value is not None:
            upsert_anchor(font, master, layer, 'BSB', descender + bsb_value, vertical=True)
        else:
            delete_anchor(font, master, layer, 'BSB')

def make_gray_color():
    return NSColor.colorWithDeviceRed_green_blue_alpha_(0.0 / 256.0, 0.0 / 256.0, 0.0 / 256.0, 0.25)

def make_magenta_color():
    return NSColor.colorWithDeviceRed_green_blue_alpha_(230.0 / 256.0, 0.0 / 256.0, 126.0 / 256.0, 1.0)

def make_cyan_color():
    return NSColor.colorWithDeviceRed_green_blue_alpha_(0.0 / 256.0, 159.0 / 256.0, 227.0 / 256.0, 1.0)

def draw_metrics_rect(font, master, layer, lsb_value, rsb_value, tsb_value, bsb_value):
    vert_width = layer.vertWidth() if callable(layer.vertWidth) else layer.vertWidth
    if vert_width is None:
        vert_width = master.ascender - master.descender
    ascender, descender = (master.ascender, master.ascender - vert_width)

    x1 = lsb_value or 0.0
    x2 = layer.width - (rsb_value or 0.0)
    y1 = ascender - (tsb_value or 0.0)
    y2 = descender + (bsb_value or 0.0)
    
    path = NSBezierPath.bezierPathWithRect_(NSMakeRect(x1, y2, x2 - x1, y1 - y2))
    path.setLineWidth_(1.0)
    path.stroke()    

def guess_anchor_direction_and_calc_distance_from_edge(location, master, layer):
    vert_width = layer.vertWidth() if callable(layer.vertWidth) else layer.vertWidth
    if vert_width is None:
        vert_width = master.ascender - master.descender
    ascender, descender = (master.ascender, master.ascender - vert_width)

    bounds = NSMakeRect(0.0, descender, layer.width, vert_width)
    center = NSPoint(bounds.origin.x + bounds.size.width / 2.0, bounds.origin.y + bounds.size.height / 2.0)
    delta  = NSPoint(location.x - center.x, location.y - center.y)
    radians = math.atan2(delta.y, delta.x)
    anchor_name = None
    distance_from_edge = None
    if -(math.pi / 4.0) <= radians <= (math.pi / 4.0):
        anchor_name = 'RSB'
        distance_from_edge = (bounds.origin.x + bounds.size.width) - location.x
    elif  (math.pi / 4.0) <= radians <= (math.pi * (3.0 / 4.0)):
        anchor_name = 'TSB'
        distance_from_edge = (bounds.origin.y + bounds.size.height) - location.y
    elif -(math.pi * (3.0 / 4.0)) <= radians <= -(math.pi / 4.0):
        anchor_name = 'BSB'
        distance_from_edge = -(bounds.origin.y - location.y)
    else:
        anchor_name = 'LSB'
        distance_from_edge = bounds.origin.x + location.x
    return anchor_name, distance_from_edge

GSInspectorView = objc.lookUpClass('GSInspectorView')
class CJKAnchorPlacementInspectorView(GSInspectorView):
    
    def acceptsFirstResponder(self):
        return True
    
class CJKAnchorPlacementNumberFormatter(NSNumberFormatter):

    def isPartialStringValid_newEditingString_errorDescription_(self, partialString, newString, error):
        if len(partialString) == 0:
            return True
        scanner = NSScanner.scannerWithString_(partialString)
        if scanner.scanInt_(None) and scanner.isAtEnd():
            return True
        NSBeep()
        return False
        
class CJKAnchorPlacementValueTransformer(NSValueTransformer):

    @classmethod
    def transformedValueClass(cls):
        return NSNumber

    @classmethod
    def allowsReverseTransformation(cls):
        return True

    def transformedValue_(self, value):
        if value is None:
            return None
        try:
            return float(value)
        except Exception as e:
            return None

    def reverseTransformedValue_(self, value):
        if value is None:
            return None
        try:
            return float(value)
        except Exception as e:
            return None

class CJKAnchorPlacementTool(SelectTool):
    
    inspectorDialogView = objc.IBOutlet()
    
    LSBValue = objc.object_property()
    RSBValue = objc.object_property()
    TSBValue = objc.object_property()
    BSBValue = objc.object_property()
    
    LSBTextField = objc.IBOutlet()
    RSBTextField = objc.IBOutlet()
    TSBTextField = objc.IBOutlet()
    BSBTextField = objc.IBOutlet()
    
    def start(self):
        self.needs_disable_update_anchors = False
    
    def settings(self):
        self.name = 'CJK Anchor Placement'
        self.loadNib('InspectorView', __file__)
        self.setNextResponder_(self.LSBTextField)
        self.LSBTextField.setNextResponder_(self.RSBTextField)
        self.RSBTextField.setNextResponder_(self.TSBTextField)
        self.TSBTextField.setNextResponder_(self.BSBTextField)
        self.BSBTextField.setNextResponder_(None)
    
    def mouseDoubleDown_(self, event):
        view = self.editViewController().graphicView()
        location = view.getActiveLocation_(event)
        layer = view.activeLayer()
        if layer:
            font = layer.parent.parent
            master = font.masters[layer.associatedMasterId or layer.layerId]
            anchor_name, distance_from_edge = guess_anchor_direction_and_calc_distance_from_edge(location, master, layer)
            if anchor_name == 'LSB':
                self.LSBValue = distance_from_edge
            elif anchor_name == 'RSB':
                self.RSBValue = distance_from_edge
            elif anchor_name == 'TSB':
                self.TSBValue = distance_from_edge
            elif anchor_name == 'BSB':
                self.BSBValue = distance_from_edge
    
    @LSBValue.setter
    def LSBValue(self, value):
        if self._LSBValue != value:
            self._LSBValue = value
            self.update_anchors()
    
    @RSBValue.setter    
    def RSBValue(self, value):
        if self._RSBValue != value:
            self._RSBValue = value
            self.update_anchors()
    
    @TSBValue.setter
    def TSBValue(self, value):
        if self._TSBValue != value:
            self._TSBValue = value
            self.update_anchors()
    
    @BSBValue.setter
    def BSBValue(self, value):
        if self._BSBValue != value:
            self._BSBValue = value
            self.update_anchors()
            
    @objc.IBAction
    def handleAction_(self, sender):
        # Values needs to be updated manually after modifying value with arrow keys.
        valueTransformer = CJKAnchorPlacementValueTransformer.alloc().init()
        self.LSBValue = valueTransformer.transformedValue_(self.LSBTextField.stringValue())
        self.RSBValue = valueTransformer.transformedValue_(self.RSBTextField.stringValue())
        self.TSBValue = valueTransformer.transformedValue_(self.TSBTextField.stringValue())
        self.BSBValue = valueTransformer.transformedValue_(self.BSBTextField.stringValue())
        self.update_anchors()
    
    def update_anchors(self):
        if not self.needs_disable_update_anchors:
            layer = self.editViewController().graphicView().activeLayer()
            if layer:
                font = layer.parent.parent
                master = font.masters[layer.associatedMasterId or layer.layerId]
                apply_values_for_anchors(font, master, layer, self.LSBValue, self.RSBValue, self.TSBValue, self.BSBValue)
            
    def sync_values(self, font, master, layer):
        if layer:
            lsb_anchor = layer.anchors['LSB'] if layer.anchors else None
            rsb_anchor = layer.anchors['RSB'] if layer.anchors else None
            tsb_anchor = layer.anchors['TSB'] if layer.anchors else None
            bsb_anchor = layer.anchors['BSB'] if layer.anchors else None
            self.needs_disable_update_anchors = True
            if lsb_anchor:
                self.LSBValue = lsb_anchor.position.x
            else:
                self.LSBValue = None
            if rsb_anchor:
                self.RSBValue = layer.width - rsb_anchor.position.x
            else:
                self.RSBValue = None
            if tsb_anchor and master:
                self.TSBValue = master.ascender - tsb_anchor.position.y
            else:
                self.TSBValue = None
            if bsb_anchor and master:
                self.BSBValue = -(master.descender - bsb_anchor.position.y)
            else:
                self.BSBValue = None
            self.needs_disable_update_anchors = False
    
    def background(self, layer):
        font = layer.parent.parent
        master = font.masters[layer.associatedMasterId or layer.layerId]
        
        arrange_anchors(font, master, layer)
        self.sync_values(font, master, layer)
        with currentGraphicsContext() as ctx:
            make_cyan_color().setStroke()
            draw_metrics_rect(font, master, layer, self.LSBValue, self.RSBValue, self.TSBValue, self.BSBValue)
    
    def __file__(self):
        return __file__
