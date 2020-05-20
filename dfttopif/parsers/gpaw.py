from pypif.obj.common import Property, Scalar

from .base import DFTParser, Value_if_true, InvalidIngesterException
import os
from pypif.obj.common.value import Value

from ase import Atoms
from ase.io import read
from ase.io.ulm import InvalidULMFileError
import ase.db

class GpawParser(DFTParser):
    '''
    Parser for GPAW calculations
    '''
    def __init__(self, files):
        super(GpawParser, self).__init__(files)
        self.settings = {}
        self.all_parsed_data = {}

    # Look for ase traj files
        def _find_traj():
            '''Searches for GPAW readable traj file and returns name '''
            traj_file = None
            for f in self._files:
                if os.path.basename(f).split('.')[-1] == 'traj':
                    try:
                        test_traj_file = read(f, format='traj')
                        if traj_file is not None:
                            raise InvalidIngesterException('Found more than one valid traj file')
                        traj_file = f
                    except InvalidULMFileError:
                        pass
                    except OSError:
                        pass
            return traj_file

        self.outputf = _find_traj()
        self.output_type = 'traj'



    # Look for appropriate txt if no traj files
        if self.outputf is None:
            for f in self._files:
                try:
                    if self._get_line('gpaw', f, return_string=False, case_sens=False):
                        if self.outputf is not None:
                            raise InvalidIngesterException('More than one output file!')
                        self.outputf = f
                except UnicodeDecodeError as e:
                    pass

            # If still cannot find GPAW outputfile, raise exception
            if self.outputf is None:
                raise InvalidIngesterException('Failed to find output file')

            self.output_type='txt'

        # Use ase db functionality to read in data to temporary ase db
        def _write_temp_asedb(self):
            '''Reads designated output file and writes it to a temporary ase db '''
            atoms = read(self.outputf)
            temp_db = ase.db.connect('temp_db.db')
            temp_db.write(atoms)
            return temp_db

        self.temp_db = _write_temp_asedb()

        # Get mode for calculation
        self.calc_mode = get_mode()


    def get_total_energy(self):
        '''Determine total energy from the temporary ase db'''
        ener = self.temp_db.get(id=1).energy
        return Property(scalars=[Scalar(value=ener)], units='eV')

    def get_mode(self):
        '''Determine calculation mode used.

        Default value pulled from https://wiki.fysik.dtu.dk/gpaw/documentation/manual.html on May 18, 2020


        Returns:
           String, Possibilities are 'fd' (finite difference real space grid), 'lcao', 'pw' (plane-wave)

        '''
        try:
            mode=self.temp_db.get(id=1).calculator_parameters['mode']['name']
        except KeyError:
            mode = 'fd'
        return mode

    def get_grid_spacing(self):
        '''Determine grid spacing from the temporary ase db

        Default value pulled from https://wiki.fysik.dtu.dk/gpaw/documentation/manual.html on May 18, 2020

        Returns: Value, None if the calculator mode was not 'fd'

        '''
        if self.calc_mode == 'fd':
            try:
                h = self.temp_db.get(id=1).calculator_parameters['h']
            except KeyError:
                h = 0.2
            return Value(scalars=[Scalar(value=h)],units='angstrom')
        return None

    def get_xc_functional(self):
        '''Determine the xc functional from the temporary ase db

        Default value pulled from https://wiki.fysik.dtu.dk/gpaw/documentation/manual.html on May 18, 2020

        '''
        try:
            xc = self.temp_db.get(id=1).calculator_parameters['xc']
        except KeyError:
            xc = 'LDA'
        return Value(scalars=[Scalar(value=xc)])

    def get_cutoff_energy(self):
        '''Determine cutoff energy if calc mode is plane wave, else returns None

        Default value pulled from https://wiki.fysik.dtu.dk/gpaw/documentation/manual.html on May 18, 2020

        '''
        if self.calc_mode == 'pw':
            try:
                ecut = self.temp_db.get(id=1).calculator_parameters['mode']['ecut']
            except KeyError:
                ecut = 340.0
            return Value(scalars=[Scalar(value=ecut)],units='eV')
        return None

    def get_KPPRA(self):
        ''' Determine the no. of k-points in the BZ times the no. of atoms

        Default value pulled from https://wiki.fysik.dtu.dk/gpaw/documentation/manual.html on May 18, 2020

        '''
        try:
            kp = self.temp_db.get(id=1).calculator_parameters['kpts']
        except KeyError:
            kp = np.array([0.])
        natoms = self.temp_db.get(id=1).natoms
        return Value(scalars=[Scalar(value=kp.prod()*natoms)])

    def get_total_magnetization(self):
        try:
            spin = self.temp_db.get(id=1).calculator_parameters['spinpol']
        except KeyError:
            return None
        if spin:
            try:
                tot_mag = self.temp_db.get(id=1).magmom
            except KeyError:
                return None
            return Property(scalars=[Scalar(value=tot_mag)],units='Bohr')
        return None

    def get_output_structure(self):
        ''' Returns ase Atoms object containing only symbols, cell, pbc, and coordinates'''
        sym = self.temp_db.get(id=1).symbols
        cell = self.temp_db.get(id=1).cell
        pbc = self.temp_db.get(id=1).pbc
        coords = self.temp_db.get(id=1).positions
        struct = Atoms(symbols=sym,cell=cell,pbc=pbc)
        struct.set_positions(coords)
        return struct

    def get_name(self): return "GPAW"

    def get_outcar(self):
        return None

    def get_incar(self):
        return None

    def get_poscar(self):
        return None


    def _get_line(self, search_string, search_file, return_string=True, case_sens=True):
        '''Return the first line containing a set of strings in a file.

        If return_string is False, we just return whether such a line
        was found. If case_sens is False, the search is case
        insensitive.

        '''
        if os.path.isfile(search_file):
            # if single search string
            if type(search_string) == type(''): search_string = [search_string]
            # if case insensitive, convert everything to lowercase
            if not case_sens: search_string = [i.lower() for i in search_string]
            with open(search_file) as fp:
                # search for the strings line by line
                for line in fp:
                    query_line = line if case_sens else line.lower()
                    if all([i in query_line for i in search_string]):
                        return line if return_string else True
                if return_string:
                    raise Exception('%s not found in %s'%(' & '.join(search_string), search_file))
                else: return False
        else: raise Exception('%s file does not exist'%search_file)
