import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / 'static/app.js').read_text()
MAPS_JS = (ROOT / 'static/maps.js').read_text()
NAVBALL_JS = (ROOT / 'static/navball.js').read_text()
INDEX_HTML = (ROOT / 'static/index.html').read_text()


class IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, _tag, attrs):
        attributes = dict(attrs)
        if attributes.get('id'):
            self.ids.add(attributes['id'])


class FrontendContractTests(unittest.TestCase):
    def test_literal_id_selectors_have_matching_elements(self):
        parser = IdCollector()
        parser.feed(INDEX_HTML)
        selected_ids = set(re.findall(r"\$\('#([a-zA-Z0-9_-]+)'\)", APP_JS + MAPS_JS))
        self.assertEqual(selected_ids - parser.ids, set())

    def test_header_includes_all_telemetry_source_states(self):
        for source in ('gps', 'nano', 'obd', 'network'):
            self.assertIn(f'id="{source}-state"', INDEX_HTML)
            self.assertIn(f"'{source}'", APP_JS)
        self.assertIn("source-connected", APP_JS)

    def test_attitude_calibration_is_explicit_and_confirmed(self):
        self.assertIn("{key: 'calibrate', label: 'CALIBRATE LEVEL'}", APP_JS)
        self.assertIn("{key: 'set-level', label: 'SET CURRENT POSITION AS LEVEL'}", APP_JS)
        self.assertIn("localStorage.setItem('ovrland.attitudeCalibration'", APP_JS)
        self.assertNotIn('detailPressPending', APP_JS)

    def test_attitude_display_uses_whole_degrees(self):
        self.assertIn('function wholeDegree(value)', APP_JS)
        self.assertIn('Math.round(value)', APP_JS)
        self.assertNotIn('pitch.toFixed(1)', APP_JS)
        self.assertNotIn('roll.toFixed(1)', APP_JS)

    def test_system_has_manual_ambient_light_reference_captures(self):
        self.assertIn('id="ambient-light-reading"', INDEX_HTML)
        self.assertIn('id="ambient-calibration-log"', INDEX_HTML)
        for condition in ('day', 'dusk', 'night'):
            self.assertIn(f'data-ambient-capture="{condition}"', INDEX_HTML)
        self.assertIn('/api/ambient-light/calibration', APP_JS)

    def test_altitude_source_is_prominent_on_both_dashboards(self):
        self.assertEqual(INDEX_HTML.count('data-altitude-label'), 2)
        self.assertIn("barometric: 'ALTITUDE / BARO EST.'", APP_JS)
        self.assertIn("gps: 'ALTITUDE / GPS'", APP_JS)
        self.assertIn('altitude-from-baro', APP_JS)
        self.assertIn('altitude-from-gps', APP_JS)

    def test_drive_orientation_reserves_its_footer_for_heading(self):
        self.assertNotIn('<span>ELEVATION</span>', INDEX_HTML)
        self.assertIn('<span>HEADING</span><strong data-value="location.heading_deg">', INDEX_HTML)

    def test_navball_uses_the_tilt_oh_shit_meter_name(self):
        self.assertIn('TILT-OH-SHIT! METER', INDEX_HTML)
        self.assertIn('TILT-OH-SHIT! SETUP', APP_JS)

    def test_tilt_warning_thresholds_are_visible_on_the_navball(self):
        self.assertIn('const cautionThreshold = 20;', NAVBALL_JS)
        self.assertIn('const alarmThreshold = 30;', NAVBALL_JS)
        self.assertIn('TILT CAUTION 20°+', NAVBALL_JS)
        self.assertIn('TILT ALARM 30°+', NAVBALL_JS)
        self.assertIn("tiltAlert === 'alarm'", APP_JS)

    def test_instrument_updates_skip_unchanged_frames(self):
        self.assertIn('pitch === attitude.pitch && roll === attitude.roll', NAVBALL_JS)
        self.assertIn('else if (moved) marker.setLatLng(position);', MAPS_JS)

    def test_module_navigation_follows_visual_order_and_system_controls(self):
        navigation = APP_JS.split('const moduleTargets = {', 1)[1].split('function activeModules()', 1)[0]
        expected = {
            'drive': ['map', 'conditions', 'attitude', 'obd'],
            'adventure': ['conditions', 'attitude', 'map', 'location', 'obd'],
            'music': ['radio', 'spotify'],
            'camp': ['window-mode', 'stop-app', 'poweroff-pi', 'record',
                     'export-log', 'export-gps-track'],
        }
        for mode, order in expected.items():
            declaration = re.search(rf"  {mode}: \[(.*?)\n  \],", navigation, re.S)
            self.assertIsNotNone(declaration, mode)
            self.assertEqual(re.findall(r"\['([^']+)'", declaration.group(1)), order)

        self.assertIn("event.action === 'down' && navigationLayer === 'tabs') setModuleFocus(0)", APP_JS)
        self.assertIn('if (ahead.length) return setModuleFocus(ahead[0].index);', APP_JS)
        self.assertIn("['window-mode', '#window-mode-toggle'", APP_JS)
        self.assertIn("['record', '#record', 'START RECORDING']", APP_JS)
        self.assertIn("['export-log', '#export-log', 'EXPORT FULL LOG']", APP_JS)
        self.assertIn("['export-gps-track', '#export-gps-track', 'EXPORT GPS TRACK']", APP_JS)
        self.assertIn("if (direction === 'up')", APP_JS)
        self.assertIn('focusMode(focusIndex);', APP_JS)
        self.assertNotIn('sectionLayerIndex', APP_JS)
        self.assertNotIn('sectionLayers', APP_JS)

    def test_window_mode_toggle_is_in_system_without_exit_warning(self):
        self.assertIn('id="window-mode-toggle"', INDEX_HTML)
        self.assertNotIn('id="fullscreen"', INDEX_HTML)
        self.assertNotIn('campWarning', APP_JS)
        self.assertNotIn('Fullscreen-Exit.wav', APP_JS)

    def test_detail_focus_replaces_and_restores_module_focus(self):
        open_detail = APP_JS.split('function openDetail(key)', 1)[1].split('function closeDetail()', 1)[0]
        close_detail = APP_JS.split('function closeDetail()', 1)[1].split('function openCalibration()', 1)[0]
        self.assertLess(open_detail.index('clearJoystickFocus();'),
                        open_detail.index('detailRestore ='))
        self.assertIn('setModuleFocus(moduleIndex);', close_detail)

    def test_detail_cleanup_removes_all_global_detail_states(self):
        close_detail = APP_JS.split('function closeDetail()', 1)[1].split('function openCalibration()', 1)[0]
        for state in ('detail-map-open', 'detail-module-open', 'detail-open'):
            self.assertIn(f"classList.remove('{state}')", close_detail)

    def test_map_restore_preserves_selected_source(self):
        restore = re.search(r'restoreDashboard\(\)\s*\{([^}]*)\}', MAPS_JS)
        self.assertIsNotNone(restore)
        self.assertIn('resize()', restore.group(1))
        self.assertNotIn("choose('osm')", restore.group(1))

    def test_telemetry_default_does_not_overwrite_active_ui_messages(self):
        self.assertIn("navigationLayer === 'tabs' && $('#detail-overlay').hidden && Date.now() >= eventHoldUntil", APP_JS)
        self.assertIn('window.dashboardEvent = showEvent', APP_JS)

    def test_radio_has_complete_joystick_control_and_station_picker(self):
        for key in ('music-prev', 'music-toggle', 'music-next', 'music-volume-down',
                    'music-volume-up', 'music-stop',
                    'music-streams'):
            self.assertIn(f"key: '{key}'", APP_JS)
        self.assertIn("['radio', '.radio-portal'", APP_JS)
        self.assertIn("['spotify', '.spotify-portal'", APP_JS)
        self.assertNotIn("['local-media'", APP_JS)
        self.assertIn("stream.display_name.toUpperCase()", APP_JS)
        self.assertIn("stream.station_name", APP_JS)
        self.assertIn("fetch('/api/music/streams')", APP_JS)
        self.assertIn('radioAudio.src = chosen.playback_url', APP_JS)
        self.assertIn('radioAudio.play()', APP_JS)
        self.assertIn("fetch(`/api/music/now-playing/${encodeURIComponent(streamId)}`)", APP_JS)
        self.assertIn("Array.from({length: 10}", APP_JS)
        self.assertIn("{key: 'back', label: 'BACK TO DASHBOARD'}", APP_JS)

if __name__ == '__main__':
    unittest.main()
