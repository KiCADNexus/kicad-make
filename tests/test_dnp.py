import logging
import unittest
from typing import List
from kmake_test_common import KmakeTestCase
from kiutils.footprint import Footprint
from kiutils.schematic import Schematic
from kiutils.board import Board

from common.kmake_helper import get_property, set_property, remove_property


class DnpTest(KmakeTestCase, unittest.TestCase):

    def __init__(self, method_name: str = "runTest") -> None:
        KmakeTestCase.__init__(self, "dnp")
        unittest.TestCase.__init__(self, method_name)

    def setUp(self) -> None:
        KmakeTestCase.setUp(self)
        self.reset_repo()

    def check_symbol(self, components: List[str], dnp: bool, dnp_field: bool = False, inbom: bool = True) -> None:
        """Check if symbol have DNP fields

        Parameters:
            components: List of designator to check
            dnp: Define if component is DNP
            dnp_field: Allow component to have a DNP field (when dnp is set to False)
            inbom: Define if component is in bom
        """

        scheet = Schematic().from_file(filepath="receiver.kicad_sch")
        component_count = len(scheet.schematicSymbols)
        components_checked = 0
        for component_id in range(0, component_count):
            symbol = scheet.schematicSymbols[component_id]
            designator = get_property(symbol, "Reference")

            if designator in components:
                if dnp_field:
                    self.assertIsNot(get_property(symbol, "DNP"), None, "Symbol doesn't have DNP property")
                else:
                    self.assertIs(get_property(symbol, "DNP"), None, "Symbol has DNP property")
                if dnp:
                    self.assertTrue(symbol.dnp, "Symbol is not DNP")
                else:
                    self.assertFalse(symbol.dnp, "Symbol is DNP")
                if inbom:
                    self.assertTrue(symbol.inBom, "Symbol is not in BOM")
                else:
                    self.assertFalse(symbol.inBom, "Symbol is in BOM")
                components_checked += 1

        self.assertEqual(components_checked, len(components), "Not all components checked, internal test error")

    def check_footprint(self, components: List[str], dnp: bool) -> None:
        """Check if footprints have `Exclude from position files` and `Exclude from bill of material` fields valid

        Parameters:
            component: List of designators to check
            dnp: Define if component is DNP
        """
        pcb = Board().from_file(filepath=self.kpro.pcb_file)
        footprints = pcb.footprints
        footprints_count = len(footprints)
        footprints_checked = 0
        for footprint_id in range(0, footprints_count):
            footprint = footprints[footprint_id]
            attributes = footprint.attributes
            designator = get_property(footprint, "Reference")
            if designator in components:
                if dnp:
                    self.assertEqual(attributes.excludeFromPosFiles, True, f"{designator} Not excluded from POS files")
                    self.assertEqual(attributes.excludeFromBom, True, f"{designator} Not excluded from BOM")
                    footprints_checked += 1
                else:
                    self.assertEqual(attributes.excludeFromPosFiles, False, f"{designator} Excluded from POS files")
                    self.assertEqual(attributes.excludeFromBom, False, f"{designator} Excluded from BOM")
                    footprints_checked += 1
        self.assertEqual(footprints_checked, len(components), "Not all components checked internal test error")

    def check_paste_layer(self, footprint: Footprint) -> int:
        """Return number of pads when solder paste layer exist"""
        paste_pads = 0
        for pad in footprint.pads:
            if ("F.Paste" in pad.layers) or ("B.Paste" in pad.layers):
                paste_pads += 1
        return paste_pads

    def check_paste(self, components: List[str], dnp: bool) -> None:
        """Check if solder paste is placed at footprint pad

        Parameters:
            components: List of designators to check
            dnp: Define if component is DNP
        """
        pcb = Board().from_file(filepath=self.kpro.pcb_file)
        footprints = pcb.footprints
        footprint_count = len(footprints)
        footprints_checked = 0
        for footprint_id in range(0, footprint_count):
            footprint = footprints[footprint_id]
            designator = get_property(footprint, "Reference")
            if designator in components:
                paste_counter = self.check_paste_layer(footprint)
                if dnp:
                    self.assertEqual(paste_counter, 0, "Paste wasnt removed from all pads")
                else:
                    self.assertEqual(paste_counter, len(footprint.pads))
                footprints_checked += 1
        self.assertEqual(len(components), footprints_checked, "Not all components checked internal test error")

    def test_list_malformed(self) -> None:
        """Test output for -l command (list malformed)"""
        with self.assertLogs(level=logging.WARNING) as log:
            self.run_test_command(["-l"])
        self.assertIn(
            "There are 3 schematic components that have their DNP properties malformed:",
            log.output[0][18:96],
        )

    def test_clean_symbol(self) -> None:
        "Test if dnp symbols have `Exlude from bill of materials` and `Do not populate` fields set correctly"
        self.check_symbol(["R1", "R2"], False, True, True)
        self.check_symbol(["R3"], True, False, True)
        self.check_symbol(["C26", "C27"], False, False, True)
        self.run_test_command([])
        self.check_symbol(["R1", "R2", "R3"], True, False, False)
        self.check_symbol(["C26", "C27"], False, False, True)

    def test_clean_footprint(self) -> None:
        "Test if DNP footprints have `Exclude from pos files` and `Exclude from bill of material` fields set correctly"
        self.check_footprint(["R1"], False)
        self.check_footprint(["R6"], False)
        self.run_test_command([])
        self.check_footprint(["R1"], True)
        self.check_footprint(["R6"], False)

    def test_remove_restore_paste(self) -> None:
        "Test if solder pasted was removed and restored from DNP components"
        self.check_paste(["R1"], False)
        self.check_paste(["C26"], False)
        self.run_test_command(["--remove-dnp-paste"])
        self.check_if_pcb_sch_opens()
        self.check_paste(["R1"], True)
        self.check_paste(["C26"], False)
        self.run_test_command(["--restore-dnp-paste"])
        self.check_paste(["R1"], False)
        self.check_paste(["C26"], False)

        self.reset_repo()
        self.check_paste(["R1"], False)
        self.run_test_command(["-rp"])
        self.check_if_pcb_sch_opens()
        self.check_paste(["R1"], True)
        self.run_test_command(["-sp"])
        self.check_paste(["R1"], False)

    def reset_repo(self) -> None:
        """Reset repository to HEAD"""
        self.project_repo.git.reset("--hard", "HEAD")
        self.project_repo.git.clean("-fd")

        # Plant few imperfections in project files
        sch = Schematic().from_file(self.target_dir / "receiver.kicad_sch")
        for s in sch.schematicSymbols:
            ref = get_property(s, "Reference")
            if ref == "R1" or ref == "R2":
                set_property(s, "DNP", "DNP")
                s.dnp = False
                s.inBom = True
            if ref == "R3":
                s.properties = remove_property(s, "DNP")
                s.dnp = True
                s.inBom = True
        sch.to_file()

        pcb = Board().from_file(self.kpro.pcb_file)
        for fp in pcb.footprints:
            ref = get_property(fp, "Reference")
            if ref == "R1":
                fp.attributes.excludeFromBom = False
                fp.attributes.excludeFromPosFiles = False
        pcb.to_file()
