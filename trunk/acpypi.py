#!/usr/bin/env python
"""
    This code is released under GNU General Public License V3.

          <<<  NO WARRANTY AT ALL!!!  >>>

    It was inspired by:

    - amb2gmx.pl (Eric Sorin, David Mobley and John Chodera)
      and depends on Antechamber and Openbabel

    - YASARA Autosmiles:
      http://www.yasara.org/autosmiles.htm (Elmar Krieger)

    - topolbuild (Bruce Ray)

    - xplo2d (G.J. Kleywegt)

    For Antechamber, please cite:
    1.  Wang, J., Wang, W., Kollman P. A.; Case, D. A. "Automatic atom type and
        bond type perception in molecular mechanical calculations". Journal of
        Molecular Graphics and Modelling , 25, 2006, 247260.
    2.  Wang, J., Wolf, R. M.; Caldwell, J. W.;Kollman, P. A.; Case, D. A.
        "Development and testing of a general AMBER force field". Journal of
        Computational Chemistry, 25, 2004, 1157-1174.

    If you use this code, I am glad if you cite:

    BATISTA, P. R.; WILTER, A.; DURHAM, E. H. A. B.; PASCUTTI, P. G. Molecular
    Dynamics Simulations Applied to the Study of Subtypes of HIV-1 Protease.
    Cell Biochemistry and Biophysics, 44, 395-404, 2006.

    Alan Wilter S. da Silva, D.Sc. - CCPN Research Associate
    Department of Biochemistry, University of Cambridge.
    80 Tennis Court Road, Cambridge CB2 1GA, UK.
    >>http://www.bio.cam.ac.uk/~awd28<<

    alanwilter _at_ gmail _dot_ com
"""

from commands import getoutput
from datetime import datetime
from shutil import copy2
from shutil import rmtree
import math
import os
import cPickle as pickle
import sys

# List of Topology Formats created by acpypi so far:
outTopols = ['gmx', 'cns']

leapGaffFile = 'leaprc.gaff'
leapAmberFile = 'oldff/leaprc.ff99' #'leaprc.ff03' #'oldff/leaprc.ff99'

cal = 4.184
Pi = 3.141594

head = "%s created by acpypi on %s\n"

date = datetime.now().ctime()

USAGE = \
"""
    acpypi -i _file_ [-c _string_] [-n _int_] [-m _int_] [-a _string_] [-f] etc.
    -i    input file name with either extension '.pdb' or '.mol2' (mandatory)
    -c    charge method: gas, bcc (default), user (user's charges in mol2 file)
    -n    net molecular charge (int), for gas default is 0
    -m    multiplicity (2S+1), default is 1
    -a    atom type, can be gaff, amber, bcc and sybyl, default is gaff
    -f    force topologies recalculation anew
    -d    for debugging purposes, keep any temporary file created
    -o    output topologies: all (default), gmx, cns
    -t    write CNS topology with allhdg-like parameters (experimental)
    -e    engine: tleap (default) or sleap (not fully matured)
"""

SLEAP_TEMPLATE = \
"""
source %(leapAmberFile)s
source %(leapGaffFile)s
set default fastbld on
%(base)s = loadpdb %(base)s.pdb
saveamberparm %(base)s %(acBase)s.top %(acBase)s.xyz
quit
"""

TLEAP_TEMPLATE = \
"""
verbosity 1
source %(leapAmberFile)s
source %(leapGaffFile)s
mods = loadamberparams frcmod
%(base)s = loadmol2 %(acMol2File)s
saveamberparm %(base)s %(acBase)s.top %(acBase)s.xyz
quit
"""

def invalidArgs():

    print USAGE
    sys.exit(1)

def parseArgs(args):

    import getopt

    options = 'hi:c:n:m:o:a:e:ftd'

    ctList = ['gas', 'bcc', 'user']
    atList = ['gaff', 'amber', 'bcc', 'sybyl']
    tpList = ['all'] + outTopols
    enList = ['sleap', 'tleap']

    try:
        opt_list, args = getopt.getopt(args, options) #, long_options)
    except:
        invalidArgs()

    d = {}

    for key, value in opt_list:
        if key in d:
            invalidArgs()

        if value == '':
            value = None

        d[key] = value

    if not d and not args:
        invalidArgs()

    not_none = ('-i', '-c', '-n', '-m','-a', '-o', '-e')

    for option in not_none:
        if option in d:
            if d[option] is None:
                invalidArgs()

    if '-c' in d.keys():
        if d['-c'] not in ctList:
            invalidArgs()

    if '-a' in d.keys():
        if d['-a'] not in atList:
            invalidArgs()

    if '-o' in d.keys():
        if d['-o'] not in tpList:
            invalidArgs()

    if '-e' in d.keys():
        if d['-e'] not in enList:
            invalidArgs()

    if '-h' in d.keys():
        invalidArgs()

    if not '-i' in d.keys():
        invalidArgs()

    if not os.path.exists(d['-i']):
        print "ERROR: input file '%s' doesn't exist" % d['-i']
        invalidArgs()

    if args:
        invalidArgs()

    return d

class ACTopol:
    """
        Class to build the AC topologies (Antechamber AmberTools 1.1)
    """

    def __init__(self, inputFile, chargeType = 'bcc', chargeVal = None,
                 multiplicity = '1', atomType = 'gaff', force = False,
            debug = False, outTopol = 'all', engine = 'tleap', allhdg = False):

        self.inputFile = inputFile
        self.rootDir = os.path.abspath('.')
        self.absInputFile = os.path.abspath(inputFile)
        if not os.path.exists(self.absInputFile):
            print "WARNING: input file doesn't exist"
        base, ext = os.path.splitext(inputFile)
        self.baseName = base # name of the input file without ext.
        self.ext = ext
        self.homeDir = self.baseName + '.acpypi'
        self.chargeType = chargeType
        self.chargeVal = chargeVal
        self.multiplicity = multiplicity
        self.atomType = atomType
        self.force = force
        self.engine = engine
        self.allhdg = allhdg
        self.acExe = getoutput('which antechamber') or None # '/Users/alan/Programmes/antechamber-1.27/exe/antechamber'
        if not self.acExe:
            print "ERROR: no 'antechamber' executable!"
            return None
        self.tleapExe = getoutput('which tleap') or None
        self.sleapExe = getoutput('which sleap') or None
        self.parmchkExe = getoutput('which parmchk') or None
        self.babelExe = getoutput('which babel') or None
        if not self.babelExe:
            print "ERROR: no 'babel' executable!"
            return None
        #self.acXyz = None
        #self.acTop = None
        acBase = base + '_AC'
        self.acXyzFileName = acBase + '.xyz'
        self.acTopFileName = acBase + '.top'
        self.debug = debug
        self.guessCharge()
        acMol2File = '%s_%s_%s.mol2' % (base, chargeType, atomType)
        self.acMol2File = acMol2File
        self.outTopols = [outTopol]
        if outTopol == 'all':
            self.outTopols = outTopols
        self.acParDict = {'base' : base, 'ext' : ext[1:], 'acBase': acBase,
                          'acMol2File' : acMol2File,
                          'leapAmberFile':leapAmberFile,
                          'leapGaffFile':leapGaffFile}

    def guessCharge(self):
        """
            Guess the charge of a system based on antechamber
            Returns None in case of error
        """
        done = False
        charge = 0
        localDir = os.path.abspath('.')
        tmpDir = '.acpypi.tmp'
        if not os.path.exists(tmpDir):
            os.mkdir(tmpDir)
        if not os.path.exists(os.path.join(tmpDir, self.inputFile)):
            copy2(self.absInputFile, tmpDir)
        os.chdir(tmpDir)

        if self.chargeType == 'user':
            if self.ext == '.mol2':
                print "Reading user's charges from mol2 file..."
                charge = self.readMol2TotalCharge(self.inputFile)
                done = True
            else:
                print "WARNING: cannot read charges from a PDB file"
                print "         using now 'bcc' method for charge"

        if not self.chargeVal and not done:
            print "WARNING: no charge value given, trying to guess one..."
            if self.ext == ".pdb":
                cmd = '%s -ipdb %s -omol2 %s.mol2' % (self.babelExe, self.inputFile,
                                                      self.baseName)
                _out = getoutput(cmd)
                print _out

            cmd = '%s -i %s.mol2 -fi mol2 -o tmp -fo mol2 -c gas -pf y' % \
                                                        (self.acExe, self.baseName)

            if self.debug:
                print "Debugging..."
                cmd = cmd.replace('-pf y', '-pf n')
            #print cmd

            log = getoutput(cmd)
            #print log
            m = log.split()
            if len(m) >= 21:
                charge = float(m[14].replace('(','').replace(')',''))
            elif len(m) == 0:
                print "An old version of Antechamber? Still trying to get charge..."
                charge = self.readMol2TotalCharge('tmp')
            else:
                print "ERROR: guessCharge failed"
                os.chdir(localDir)
                print log
                return None

        charge = int(charge)
        self.chargeVal = str(charge)
        print "... charge set to", charge
        os.chdir(localDir)

    def readMol2TotalCharge(self, mol2File):
        """Reads the charges in given mol2 file and returns the total
        """
        charge = 0.0
        ll = []
        cmd = '%s -i %s -fi mol2 -o tmp -fo mol2 -c wc -cf tmp.crg -pf y' % \
                                                        (self.acExe, mol2File)
        if self.debug:
            print "Debugging..."
            cmd = cmd.replace('-pf y', '-pf n')

        log = getoutput(cmd)

        if log.isspace():
            tmpFile = open('tmp.crg', 'r')
            tmpData = tmpFile.readlines()
            for line in tmpData:
                ll += line.split()
            charge = sum(map(float,ll))

        return charge

    def execAntechamber(self, chargeType = None, atomType = None):
        """
            To call Antechamber and execute it

Usage: antechamber -i   input file name
                   -fi  input file format
                   -o   output file name
                   -fo  output file format
                   -c   charge method
                   -cf  charge file name
                   -nc  net molecular charge (int)
                   -a   additional file name
                   -fa  additional file format
                   -ao  additional file operation
                        crd : only read in coordinate
                        crg: only read in charge
                        name  : only read in atom name
                        type  : only read in atom type
                        bond  : only read in bond type
                   -m   multiplicity (2S+1), default is 1
                   -rn  residue name, if not available in the input file, default is MOL
                   -rf  residue toplogy file name in prep input file, default is molecule.res
                   -ch  check file name in gaussian input file, default is molecule
                   -ek  empirical calculation (mopac or divcon) keyword in a pair of quotation marks
                   -gk  gaussian keyword in a pair of quotation marks
                   -df  use divcon flag, 1 - use divcon; 0 - use mopac (default)
                   -at  atom type, can be gaff, amber, bcc and sybyl, default is gaff
                   -du  check atom name duplications, can be yes(y) or no(n), default is yes
                   -j   atom type and bond type prediction index, default is 4
                        0    : no assignment
                        1    : atom type
                        2    : full  bond types
                        3    : part  bond types
                        4    : atom and full bond type
                        5    : atom and part bond type
                   -s   status information, can be 0 (brief), 1 (the default) and 2 (verbose)
                   -pf  remove the intermediate files: can be yes (y) and no (n), default is no
                   -i -o -fi and -fo must appear in command lines and the others are optional

                             List of the File Formats

                file format type  abbre. index | file format type abbre. index
                ---------------------------------------------------------------
                Antechamber        ac       1  | Sybyl Mol2         mol2    2
                PDB                pdb      3  | Modified PDB       mpdb    4
                AMBER PREP (int)   prepi    5  | AMBER PREP (car)   prepc   6
                Gaussian Z-Matrix  gzmat    7  | Gaussian Cartesian gcrt    8
                Mopac Internal     mopint   9  | Mopac Cartesian    mopcrt 10
                Gaussian Output    gout    11  | Mopac Output       mopout 12
                Alchemy            alc     13  | CSD                csd    14
                MDL                mdl     15  | Hyper              hin    16
                AMBER Restart      rst     17  | Jaguar Cartesian   jcrt   18
                Jaguar Z-Matrix    jzmat   19  | Jaguar Output      jout   20
                Divcon Input       divcrt  21  | Divcon Output      divout 22
                Charmm             charmm  23
                --------------------------------------------------------------

                AMBER restart file can only be read in as additional file.

                             List of the Charge Methods

                charge method     abbre.  index | charge method      abbre. index
                ----------------------------------------------------------------
                RESP               resp     1  |  AM1-BCC            bcc     2
                CM1                cm1      3  |  CM2                cm2     4
                ESP (Kollman)      esp      5  |  Mulliken           mul     6
                Gasteiger          gas      7  |  Read in charge     rc      8
                Write out charge   wc       9  |  Delete Charge      dc     10
                ----------------------------------------------------------------
        """

        print "Executing Antechamber..."

        self.makeDir()

        ct = chargeType or self.chargeType
        at = atomType or self.atomType

        cmd = '%s -i %s -fi %s -o %s -fo mol2 -c %s -nc %s -m %s -s 2 -df 0 -at\
        %s -pf y' % (self.acExe, self.inputFile, self.ext[1:], self.acMol2File,
                     ct, self.chargeVal, self.multiplicity, at)

        if self.debug:
            print "Debugging..."
            cmd = cmd.replace('-pf y', '-pf n')

        if os.path.exists(self.acMol2File) and not self.force:
            print "AC output file present... doing nothing"
        else:
            try: os.remove(self.acMol2File)
            except: pass
            self.acLog = getoutput(cmd)

        if os.path.exists(self.acMol2File):
            print "==> Antechamber OK"
        else:
            print self.acLog
            return True

    def delOutputFiles(self):
        delFiles = ['mopac.in', 'mopac.pdb', 'mopac.out', 'tleap.in','sleap.in',
                    'frcmod', 'divcon.pdb', 'leap.log', 'fixbo.log',
                    'addhs.log', 'ac_tmp_ot.mol2', 'frcmod.ac_tmp',
                    'fragment.mol2', '../.acpypi.tmp']
        print "Removing temporary files..."
        for file in delFiles:
            file = os.path.join(self.absHomeDir, file)
            if os.path.exists(file):
                if os.path.isdir(file):
                    rmtree(file)
                else:
                    os.remove(file)

    def checkXyzAndTopFiles(self):
        fileXyz = self.acXyzFileName
        fileTop = self.acTopFileName
        if os.path.exists(fileXyz) and os.path.exists(fileTop):
            #self.acXyz = fileXyz
            #self.acTop = fileTop
            return True
        return False

    def execSleap(self):

        self.makeDir()

        if self.ext == '.mol2':
            print "WARNING: Sleap doesn't work with mol2 files yet..."
            return True

        if self.chargeType != 'bcc':
            print "WARNING: Sleap works only with bcc charge method"
            return True

        if self.atomType != 'gaff':
            print "WARNING: Sleap works only with gaff atom type"
            return True

        sleapScpt = SLEAP_TEMPLATE % self.acParDict

        fp = open('sleap.in','w')
        fp.write(sleapScpt)
        fp.close()

        cmd = '%s -f sleap.in' % self.sleapExe

        if self.checkXyzAndTopFiles() and not self.force:
            print "Topologies files already present... doing nothing"
        else:
            try: os.remove(self.acTopFileName) ; os.remove(self.acXyzFileName)
            except: pass
            print "Executing Sleap..."
            self.sleapLog = getoutput(cmd)

            if self.checkXyzAndTopFiles():
                print "==> Sleap OK"
            else:
                print self.sleapLog
                return True

    def execTleap(self):

        self.makeDir()

        if self.ext == ".pdb":
            print '... converting pdb input file to mol2 input file'
            if self.convertPdbToMol2():
                print "ERROR: convertPdbToMol2 failed"

        #print self.chargeVal

        if self.execAntechamber():
            print "ERROR: Antechamber failed"

        if self.execParmchk():
            print "ERROR: Parmchk failed"

        tleapScpt = TLEAP_TEMPLATE % self.acParDict

        fp = open('tleap.in','w')
        fp.write(tleapScpt)
        fp.close()

        cmd = '%s -f tleap.in' % self.tleapExe

        if self.checkXyzAndTopFiles() and not self.force:
            print "Topologies files already present... doing nothing"
        else:
            try: os.remove(self.acTopFileName) ; os.remove(self.acXyzFileName)
            except: pass
            self.tleapLog = getoutput(cmd)

        if self.checkXyzAndTopFiles():
            print "==> Tleap OK"
        else:
            print self.tleapLog
            return True

    def execParmchk(self):

        self.makeDir()
        cmd = '%s -i %s -f mol2 -o frcmod' % (self.parmchkExe, self.acMol2File)
        self.parmchkLog = getoutput(cmd)

        if os.path.exists('frcmod'):
            print "==> Parmchk OK"
        else:
            print self.parmchkLog
            return True

    def convertPdbToMol2(self):
        if self.ext == '.pdb':
            if self.execBabel():
                print "ERROR: convert pdb to mol2 via babel failed"
                return True

    def execBabel(self):

        self.makeDir()

        cmd = '%s -ipdb %s.pdb -omol2 %s.mol2' % (self.babelExe, self.baseName,
                                                  self.baseName)
        self.babelLog = getoutput(cmd)
        self.ext = '.mol2'
        self.inputFile = self.baseName+self.ext
        self.acParDict['ext'] = 'mol2'
        if os.path.exists(self.inputFile):
            print "==> Babel OK"
        else:
            print self.babelLog
            return True

    def makeDir(self):

        os.chdir(self.rootDir)
        self.absHomeDir = os.path.abspath(self.homeDir)
        if not os.path.exists(self.homeDir):
            os.mkdir(self.homeDir)
        os.chdir(self.homeDir)
        copy2(self.absInputFile, '.')

        return True

    def createACTopol(self):
        """
            If successful, Amber Top and Xyz files will be generated
        """
        sleap = False
        if self.engine == 'sleap':
            sleap = self.execSleap()
        if sleap:
            print "ERROR: Sleap failed"
            print "... trying Tleap"
            if self.execTleap():
                print "ERROR: Tleap failed"
        if self.engine == 'tleap':
            if self.execTleap():
                print "ERROR: Tleap failed"
        if not self.debug:
            self.delOutputFiles()

        #self.pickleSave()

    def pickleSave(self):
        """
            To restore:
                from acpypi import *
                import cPickle as pickle
                o = pickle.load(open('DDD.pkl'))
                NB: It fails to restore with ipython in Mac (Linux OK)
        """
        pklFile = self.baseName+".pkl"
        if not os.path.exists(pklFile):
            print "Writing pickle file %s" % pklFile
            pickle.dump(self, open(pklFile,"w"))
        elif self.force:
            print "Overwriting pickle file %s" % pklFile
            pickle.dump(self, open(pklFile,"w"))
        else:
            print "Pickle file %s already present... doing nothing" % pklFile

    def createMolTopol(self):
        """
            Create molTop obj
        """
        self.molTopol = MolTopol(self)
        if self.outTopols:
            if 'cns' in self.outTopols:
                self.molTopol.writeCnsTopolFiles()
            if 'gmx' in self.outTopols:
                self.molTopol.writeGromacsTopolFiles()
        self.pickleSave()

class MolTopol:
    """"
        http://amber.scripps.edu/formats.html (not updated to amber 10 yet)
        Parser, take information in AC xyz and top files and convert to objects
        INPUTS: acFileXyz and acFileTop
        RETURN: molTopol obj or None
    """
    def __init__(self, acTopolObj = None, acFileXyz = None, acFileTop = None):

        self.allhdg = False
        if acTopolObj:
            if not acFileXyz: acFileXyz = acTopolObj.acXyzFileName
            if not acFileTop: acFileTop = acTopolObj.acTopFileName
            self._parent = acTopolObj
            self.allhdg = self._parent.allhdg
        if not os.path.exists(acFileXyz) and not os.path.exists(acFileTop):
            print "ERROR: Files '%s' and '%s' don't exist"
            print "       molTopol object won't be created"
            return None

        self.xyzFileData = open(acFileXyz, 'r').readlines()
        self.topFileData = open(acFileTop, 'r').readlines()

#        self.pointers = self.getFlagData('POINTERS')

        self.getResidueLabel()
        self.baseName = self.residueLabel # 3 caps letters
        if acTopolObj:
            self.baseName = acTopolObj.baseName

        self.getAtoms()

        self.getBonds()

        self.getAngles()

        self.getDihedrals()

        self.setAtomPairs()

        self.getExcludedAtoms()

        # a list of FLAGS from acTopFile that matter
#        self.flags = ( 'POINTERS', 'ATOM_NAME', 'CHARGE', 'MASS', 'ATOM_TYPE_INDEX',
#                  'NUMBER_EXCLUDED_ATOMS', 'NONBONDED_PARM_INDEX',
#                  'RESIDUE_LABEL', 'BOND_FORCE_CONSTANT', 'BOND_EQUIL_VALUE',
#                  'ANGLE_FORCE_CONSTANT', 'ANGLE_EQUIL_VALUE',
#                  'DIHEDRAL_FORCE_CONSTANT', 'DIHEDRAL_PERIODICITY',
#                  'DIHEDRAL_PHASE', 'AMBER_ATOM_TYPE' )

    def getFlagData(self, flag):
        """
            For a given acFileTop flag, return a list of the data related
        """
        block = False
        tFlag = '%FLAG ' + flag
        data = ''

        for rawLine in self.topFileData:
            line = rawLine[:-1]
            if tFlag in line:
                block = True
                continue
            if block and '%FLAG ' in line: break
            if block:
                if '%FORMAT' in line:
                    line = line.strip().strip('%FORMAT()').split('.')[0]
                    for c in line:
                        if c.isalpha():
                            f = int(line.split(c)[1])
                            break
                    continue
                data += line
        # data need format
        fdata = ''
        for i in range(0,len(data),f):
            fdata += (data[i:i+f])+' '
        sdata = fdata.split()
        if '+' and '.' in data: # it's a float
            ndata = map(float, sdata)
        else:
            try: # try if it's integer
                ndata = map(int, sdata)
            except: # it's string
                ndata = sdata
        return ndata # a list

    def getCoords(self):
        """
            For a given acFileXyz file, return a list of coords as:
            [[x1,y1,z1],[x2,y2,z2], etc.]
        """
        data = ''
        for rawLine in self.xyzFileData[2:]:
            line = rawLine[:-1]
            data += line
        sdata = data.split()
        ndata = map(float, sdata)

        gdata = []
        for i in range(0, len(ndata), 3):
            gdata.append([ndata[i], ndata[i+1], ndata[i+2]])

        return gdata

    def getResidueLabel(self):
        """
            Get a 3 capital letters code from acFileTop
        """
        residueLabel = self.getFlagData('RESIDUE_LABEL')
        self.residueLabel = residueLabel[0]

    def getAtoms(self):
        """
            Set a list with all atoms objects build from dat in acFileTop
            Set also if molTopol atom type system is gaff or amber
            Set also list atomTypes
            Set also molTopol total charge
        """
        atomNameList = self.getFlagData('ATOM_NAME')
        atomTypeNameList = self.getFlagData('AMBER_ATOM_TYPE')
        self._atomTypeNameList = atomTypeNameList
        massList = self.getFlagData('MASS')
        chargeList = self.getFlagData('CHARGE')
        #uniqAtomTypeId = self.getFlagData('ATOM_TYPE_INDEX') # for LJ
        balanceChargeList = self.balanceCharges(chargeList)
        coords = self.getCoords()
        ACOEFs, BCOEFs = self.getABCOEFs()

        atoms = []
        atomTypes = []
        tmpList = [] # a list with unique atom types
        totalCharge = 0.0
        for atomName in atomNameList:
            id = atomNameList.index(atomName)
            atomTypeName = atomTypeNameList[id]
            mass = massList[id]
            charge = balanceChargeList[id]
            totalCharge += charge
            coord = coords[id]
            ACOEF = ACOEFs[id]
            BCOEF = BCOEFs[id]
            atomType = AtomType(atomTypeName, mass, ACOEF, BCOEF)
            if atomTypeName not in tmpList:
                tmpList.append(atomTypeName)
                atomTypes.append(atomType)
            atom = Atom(atomName, atomType, mass, charge, coord, ACOEF, BCOEF)
            atoms.append(atom)

        if atomTypeName[0].islower:
            self.atomTypeSystem = 'gaff'
        else:
            self.atomTypeSystem = 'amber'

        self.totalCharge = int(totalCharge)

        self.atoms = atoms
        self.atomTypes = atomTypes

    def getBonds(self):
        uniqKbList = self.getFlagData('BOND_FORCE_CONSTANT')
        uniqReqList = self.getFlagData('BOND_EQUIL_VALUE')
        bondCodeHList = self.getFlagData('BONDS_INC_HYDROGEN')
        bondCodeNonHList = self.getFlagData('BONDS_WITHOUT_HYDROGEN')
        bondCodeList = bondCodeHList + bondCodeNonHList
        bonds = []
        for i in range(0, len(bondCodeList), 3):
            idAtom1 = bondCodeList[i] / 3 # remember python starts with id 0
            idAtom2 = bondCodeList[i+1] / 3
            bondTypeId = bondCodeList[i+2] - 1
            atom1 = self.atoms[idAtom1]
            atom2 = self.atoms[idAtom2]
            kb = uniqKbList[bondTypeId]
            req = uniqReqList[bondTypeId]
            atoms = [atom1, atom2]
            bond = Bond(atoms, kb, req)
            bonds.append(bond)
        self.bonds = bonds

    def getAngles(self):
        uniqKtList = self.getFlagData('ANGLE_FORCE_CONSTANT')
        uniqTeqList = self.getFlagData('ANGLE_EQUIL_VALUE')
        # for list below, true atom number = index/3 + 1
        angleCodeHList = self.getFlagData('ANGLES_INC_HYDROGEN')
        angleCodeNonHList = self.getFlagData('ANGLES_WITHOUT_HYDROGEN')
        angleCodeList = angleCodeHList + angleCodeNonHList
        angles = []
        for i in range(0, len(angleCodeList), 4):
            idAtom1 = angleCodeList[i] / 3 # remember python starts with id 0
            idAtom2 = angleCodeList[i+1] / 3
            idAtom3 = angleCodeList[i+2] / 3
            angleTypeId = angleCodeList[i+3] - 1
            atom1 = self.atoms[idAtom1]
            atom2 = self.atoms[idAtom2]
            atom3 = self.atoms[idAtom3]
            kt = uniqKtList[angleTypeId]
            teq = uniqTeqList[angleTypeId] # angle given in rad in prmtop
            atoms = [atom1, atom2, atom3]
            angle = Angle(atoms, kt, teq)
            angles.append(angle)
        self.angles = angles

    def getDihedrals(self):
        uniqKpList = self.getFlagData('DIHEDRAL_FORCE_CONSTANT')
        uniqPeriodList = self.getFlagData('DIHEDRAL_PERIODICITY')
        uniqPhaseList = self.getFlagData('DIHEDRAL_PHASE')
        # for list below, true atom number = abs(index)/3 + 1
        dihCodeHList = self.getFlagData('DIHEDRALS_INC_HYDROGEN')
        dihCodeNonHList = self.getFlagData('DIHEDRALS_WITHOUT_HYDROGEN')
        dihCodeList = dihCodeHList + dihCodeNonHList
        properDih = []
        improperDih = []
        condProperDih = [] # list of dihedrals condensed by the same quartet
        for i in range(0, len(dihCodeList), 5):
            idAtom1 = dihCodeList[i] / 3 # remember python starts with id 0
            idAtom2 = dihCodeList[i+1] / 3
            # 3 and 4 indexes can be negative: if id3 < 0, end group interations
            # in amber are to be ignored; if id4 < 0, dihedral is improper
            idAtom3raw = dihCodeList[i+2] / 3 # can be negative
            idAtom4raw = dihCodeList[i+3] / 3 # can be negative -> Improper
            idAtom3 = abs(idAtom3raw)
            idAtom4 = abs(idAtom4raw)
            dihTypeId = dihCodeList[i+4] - 1
            atom1 = self.atoms[idAtom1]
            atom2 = self.atoms[idAtom2]
            atom3 = self.atoms[idAtom3]
            atom4 = self.atoms[idAtom4]
            kPhi = uniqKpList[dihTypeId] # already divided by IDIVF
            period = int(uniqPeriodList[dihTypeId]) # integer
            phase = uniqPhaseList[dihTypeId]# angle given in rad in prmtop
            atoms = [atom1, atom2, atom3, atom4]
            dihedral = Dihedral(atoms, kPhi, period, phase)
            if idAtom4raw > 0:
                try: atomsPrev = properDih[-1].atoms
                except: atomsPrev = []
                properDih.append(dihedral)
                if idAtom3raw < 0 and atomsPrev == atoms:
                    condProperDih[-1].append(dihedral)
                else:
                    condProperDih.append([dihedral])
            else:
                improperDih.append(dihedral)

        self.properDihedrals = properDih
        self.improperDihedrals = improperDih
        self.condensedProperDihedrals = condProperDih # [[],[],...]

    def setAtomPairs(self):
        """
            Set a list of pair of atoms pertinent to interaction 1-4 for vdw.
        """
        atomPairs = []
        for item in self.condensedProperDihedrals:
            dih = item[0]
            atom1 = dih.atoms[0]
            atom2 = dih.atoms[3]
            atomPairs.append([atom1, atom2])
        self.atomPairs = atomPairs # [[atom1, atom2], ...]

    def getExcludedAtoms(self):
        """
            Returns a list of atoms with a list of its excluded atoms up to 3rd
            neighbour.
            It's implicitly indexed, i.e., a sequence of atoms in position n in
            the excludedAtomsList corresponds to atom n (self.atoms) and so on.
        """
        excludedAtomsIdList = self.getFlagData('EXCLUDED_ATOMS_LIST')
        numberExcludedAtoms = self.getFlagData('NUMBER_EXCLUDED_ATOMS')
        atoms = self.atoms
        interval = 0
        excludedAtomsList = []
        for number in numberExcludedAtoms:
            temp = excludedAtomsIdList[interval:interval + number]
            if temp == [0]:
                excludedAtomsList.append([])
            else:
                excludedAtomsList.append([atoms[a-1] for a in temp])
            interval += number
        self.excludedAtoms = excludedAtomsList

    def balanceCharges(self, chargeList):
        """
            Note that python is very annoying about floating points.
            Even after balance, there will always be some residue of order e-12
            to e-16, which is believed to vanished once one writes a topology
            file, say, for CNS or GMX, where floats are represented with 4 or 5
            maximum decimals.
        """
        total = sum(chargeList)/18.2223
        maxVal = max(chargeList)
        minVal = min(chargeList)
        if abs(maxVal) >= abs(minVal): lim = maxVal
        else: lim = minVal
        limId = chargeList.index(lim)
        diff = (total - int(total)) * 18.2223
        fix = lim - diff
        chargeList[limId] = fix
        return chargeList

    def getABCOEFs(self):
        uniqAtomTypeIdList = self.getFlagData('ATOM_TYPE_INDEX')
        nonBonIdList = self.getFlagData('NONBONDED_PARM_INDEX')
        rawACOEFs = self.getFlagData('LENNARD_JONES_ACOEF')
        rawBCOEFs = self.getFlagData('LENNARD_JONES_BCOEF')
        #print nonBonIdList, len(nonBonIdList), rawACOEFs, len(rawACOEFs)
        ACOEFs = []
        BCOEFs = []
        ntypes = max(uniqAtomTypeIdList)
        for atName in self._atomTypeNameList:
            id = self._atomTypeNameList.index(atName)
            atomTypeId = uniqAtomTypeIdList[id]
            index = ntypes * (atomTypeId - 1) + atomTypeId
            nonBondId = nonBonIdList[index - 1]
            #print "*****", index, ntypes, atName, id, atomTypeId, nonBondId
            ACOEFs.append(rawACOEFs[nonBondId - 1])
            BCOEFs.append(rawBCOEFs[nonBondId - 1])
        #print ACOEFs
        return ACOEFs, BCOEFs

    def setProperDihedralsCoefRB(self):
        """
            It takes self.condensedProperDihedrals and returns
            self.properDihedralsCoefRB, a reduced list of quartet atoms + RB.
            Coeficients ready for GMX (multiplied by 4.184)

            self.properDihedralsCoefRB = [ [atom1,..., atom4], C[0:5] ]

            For proper dihedrals: a quartet of atoms may appear with more than
            one set of parameters and to convert to GMX they are treated as RBs.

            The resulting coefs calculated here may look slighted different from
            the ones calculated by amb2gmx.pl because python is taken full float
            number from prmtop and not rounded numbers from rdparm.out as
            amb2gmx.pl does.
        """
        properDihedralsCoefRB = []
        for item in self.condensedProperDihedrals:
            V = 6 * [0.0]
            C = 6 * [0.0]
            for dih in item:
                period = dih.period
                kPhi = dih.kPhi # in rad
                phase = dih.phase
                if kPhi > 0: V[period] = 2 * kPhi * cal
                if period == 1:
                    C[0] += 0.5 * V[period]
                    if phase == 0.0:
                        C[1] -= 0.5 * V[period]
                    else:
                        C[1] += 0.5 * V[period]
                elif period == 2:
                    if phase == Pi:
                        C[0] += V[period]
                        C[2] -= V[period]
                    else:
                        C[2] += V[period]
                elif period == 3:
                    C[0] += 0.5 * V[period]
                    if phase == 0.0:
                        C[1] += 1.5 * V[period]
                        C[3] -= 2 * V[period]
                    else:
                        C[1] -= 1.5 * V[period]
                        C[3] += 2 * V[period]
                elif period == 4:
                    if phase == Pi:
                        C[2] += 4 * V[period]
                        C[4] -= 4 * V[period]
                    else:
                        C[0] += V[period]
                        C[2] -= 4 * V[period]
                        C[4] += 4 * V[period]
                #print kPhi, period, phase, V, C
            properDihedralsCoefRB.append([item[0].atoms,C])

        self.properDihedralsCoefRB = properDihedralsCoefRB

    def writePdb(self, file):
        """
            Write a new PDB file with the atom names defined by Antechamber
            Input: file path string
            The format generated here use is slightly different from
            http://www.wwpdb.org/documentation/format23/sect9.html respected to
            atom name
        """
        #TODO: assuming only one residue ('1')
        pdbFile = open(file, 'w')
        fbase = os.path.basename(file)
        pdbFile.write("REMARK "+ head % (fbase, date))
        for atom in self.atoms:
            id = self.atoms.index(atom) + 1
            aName = atom.atomName
            if len(aName) != 4:
                aName = ' ' + aName
            s = aName[1]
            rName = self.residueLabel
            x = atom.coords[0]
            y = atom.coords[1]
            z = atom.coords[2]
            line = "%-6s%5d %-5s%3s Z%4d%s%8.3f%8.3f%8.3f%6.2f%6.2f%s%2s\n" % \
            ('ATOM', id, aName, rName, 1, 4*' ', x, y, z, 1.0, 0.0, 10*' ', s)
            pdbFile.write(line)
        pdbFile.write('END\n')

    def writeGromacsTopolFiles(self):
        """
            # from ~/Programmes/amber10/dat/leap/parm/gaff.dat
            #atom type        atomic mass        atomic polarizability        comments
            ca                12.01                 0.360                    Sp2 C in pure aromatic systems
            ha                1.008                 0.135                    H bonded to aromatic carbon

            #bonded atoms        harmonic force kcal/mol/A^2       eq. dist. Ang.  comments
            ca-ha                  344.3*                           1.087**         SOURCE3  1496    0.0024    0.0045
            * for gmx: 344.3 * 4.184 * 100 * 2 = 288110 kJ/mol/nm^2 (why factor 2?)
            ** convert Ang to nm ( div by 10) for gmx: 1.087 A = 0.1087 nm
            # CA HA         1    0.10800   307105.6 ; ged from 340. bsd on C6H6 nmodes; PHE,TRP,TYR (from ffamber99bon.itp)
            # CA-HA  367.0    1.080       changed from 340. bsd on C6H6 nmodes; PHE,TRP,TYR (from parm99.dat)

            # angle        HF kcal/mol/rad^2    eq angle degrees     comments
            ca-ca-ha        48.5*             120.01                SOURCE3 2980   0.1509   0.2511
            * to convert to gmx: 48.5 * 4.184 * 2 = 405.848 kJ/mol/rad^2 (why factor 2?)
            # CA  CA  HA           1   120.000    418.400 ; new99 (from ffamber99bon.itp)
            # CA-CA-HA    50.0      120.00 (from parm99.dat)

            # dihedral    idivf        barrier hight/2 kcal/mol  phase degrees       periodicity     comments
            X -ca-ca-X    4           14.500*                     180.000                2.000             intrpol.bsd.on C6H6
            * to convert to gmx: 14.5/4 * 4.184 * 2 (?) (yes in amb2gmx, no in topolbuild, why?) = 30.334 or 15.167 kJ/mol
            # X -CA-CA-X    4   14.50        180.0             2.         intrpol.bsd.on C6H6 (from parm99.dat)
            # X   CA  CA  X     3    30.33400     0.00000   -30.33400     0.00000     0.00000     0.00000   ; intrpol.bsd.on C6H6
            ;propers treated as RBs in GROMACS to use combine multiple AMBER torsions per quartet (from ffamber99bon.itp)

            # impr. dihedral        barrier hight/2      phase degrees       periodicity     comments
            X -X -ca-ha             1.1*                  180.                      2.                   bsd.on C6H6 nmodes
            * to convert to gmx: 1.1 * 4.184 = 4.6024 kJ/mol/rad^2
            # X -X -CA-HA         1.1          180.          2.           bsd.on C6H6 nmodes (from parm99.dat)
            # X   X   CA  HA       1      180.00     4.60240     2      ; bsd.on C6H6 nmodes
            ;impropers treated as propers in GROMACS to use correct AMBER analytical function (from ffamber99bon.itp)

            # 6-12 parms     sigma = 2 * r * 2^(-1/6)    epsilon
            # atomtype        radius Ang.                    pot. well depth kcal/mol      comments
              ha                  1.4590*                      0.0150**                         Spellmeyer
              ca                  1.9080                    0.0860                            OPLS
            * to convert to gmx:
                sigma = 1.4590 * 2^(-1/6) * 2 = 2 * 1.29982 Ang. = 2 * 0.129982 nm  = 1.4590 * 2^(5/6)/10 =  0.259964 nm
            ** to convert to gmx: 0.0150 * 4.184 = 0.06276 kJ/mol
            # amber99_3    CA     0.0000  0.0000  A   3.39967e-01  3.59824e-01 (from ffamber99nb.itp)
            # amber99_22   HA     0.0000  0.0000  A   2.59964e-01  6.27600e-02 (from ffamber99nb.itp)
            # C*          1.9080  0.0860             Spellmeyer
            # HA          1.4590  0.0150             Spellmeyer (from parm99.dat)
            # to convert r and epsilon to ACOEF and BCOEF
            # ACOEF = sqrt(e1*e2) * (r1 + r2)^12 ; BCOEF = 2 * sqrt(e1*e2) * (r1 + r2)^6 = 2 * ACOEF/(r1+r2)^6
            # to convert ACOEF and BCOEF to r and espsilon
            # r = 0.5 * (2*ACOEF/BCOEF)^(1/6); ep = BCOEF^2/(4*ACOEF)
            # to convert ACOEF and BCOEF to sigma and epsilon (GMX)
            # sigma = (ACOEF/BCOEF)^(1/6) * 0.1 ; epsilon = 4.184 * BCOEF^2/(4*ACOEF)
            #   ca   ca       819971.66        531.10
            #   ca   ha        76245.15        104.66
            #   ha   ha         5716.30         18.52

            For proper dihedrals: a quartet of atoms may appear with more than
            one set of parameters and to convert to GMX they are treated as RBs;
            use the algorithm:
              for(my $j=$i;$j<=$lines;$j++){
                my $period = $pn{$j};
                if($pk{$j}>0) {
                  $V[$period] = 2*$pk{$j}*$cal;
                }
                # assign V values to C values as predefined #
                if($period==1){
                  $C[0]+=0.5*$V[$period];
                  if($phase{$j}==0){
                    $C[1]-=0.5*$V[$period];
                  }else{
                    $C[1]+=0.5*$V[$period];
                  }
                }elsif($period==2){
                  if(($phase{$j}==180)||($phase{$j}==3.14)){
                    $C[0]+=$V[$period];
                    $C[2]-=$V[$period];
                  }else{
                    $C[2]+=$V[$period];
                  }
                }elsif($period==3){
                  $C[0]+=0.5*$V[$period];
                  if($phase{$j}==0){
                    $C[1]+=1.5*$V[$period];
                    $C[3]-=2*$V[$period];
                  }else{
                    $C[1]-=1.5*$V[$period];
                    $C[3]+=2*$V[$period];
                  }
                }elsif($period==4){
                  if(($phase{$j}==180)||($phase{$j}==3.14)){
                    $C[2]+=4*$V[$period];
                    $C[4]-=4*$V[$period];
                  }else{
                    $C[0]+=$V[$period];
                    $C[2]-=4*$V[$period];
                    $C[4]+=4*$V[$period];
                  }
                }
              }
        """
        #gmxDir = os.path.join(os.path.abspath('.'),'GMX')
        gmxDir = os.path.abspath('.')
        #if not os.path.exists(gmxDir):
        #    os.mkdir(gmxDir)

        top = self.baseName+'_GMX.top'
        itp = self.baseName+'_GMX.itp'
        gro = self.baseName+'_GMX.gro'
        topFileName = os.path.join(gmxDir, top)
        groFileName = os.path.join(gmxDir, gro)
        itpFileName = os.path.join(gmxDir, itp)

        self.GmxTopFileName = topFileName
        self.GmxItpFileName = itpFileName
        self.GmxGroFileName = groFileName

        topFile = open(topFileName, 'w')
        groFile = open(groFileName, 'w')
        itpFile = open(itpFileName, 'w')

        headDefault = \
"""
[ defaults ]
; nbfunc        comb-rule       gen-pairs       fudgeLJ fudgeQQ
1               2               yes             0.5     0.8333
"""
        headItp = \
"""
; Include %s topology
#include "%s"
"""
        headSystem = \
"""
[ system ]
System %s, Residue %s
"""
        headMols = \
"""
[ molecules ]
; Compound        nmols
 %-16s 1
"""
        headAtomtypes = \
"""
[ atomtypes ]
;name   bond_type     mass     charge   ptype   sigma         epsilon       Amb
"""
        headMoleculetype = \
"""
[ moleculetype ]
;name            nrexcl
 %-16s 3
"""
        headAtoms = \
"""
[ atoms ]
;   nr  type  resi  res  atom  cgnr     charge      mass       typeB    chargeB
"""
        headBonds = \
"""
[ bonds ]
;   ai     aj funct   r             k
"""
        headPairs = \
"""
[ pairs ]
;   ai     aj    funct
"""
        headAngles = \
"""
[ angles ]
;   ai     aj     ak    funct   theta         cth
"""
        headProDih = \
"""
[ dihedrals ] ; propers
; treated as RBs in GROMACS to use combine multiple AMBER torsions per quartet
; i   j   k   l func   C0        C1        C2        C3        C4        C5
"""
        headImpDih = \
"""
[ dihedrals ] ; impropers
; treated as propers in GROMACS to use correct AMBER analytical function
; i   j   k   l func  phase     kd      pn
"""

        print "Writing GROMACS TOP file\n"
        topFile.write("; " + head % (top, date))
        topFile.write(headDefault)
        topFile.write(headItp % (itp, itp))
        topFile.write(headSystem % (self.baseName, self.residueLabel))
        topFile.write(headMols % self.baseName)

        print "Writing GROMACS ITP file\n"
        itpFile.write("; " + head % (itp, date))
        itpFile.write(headAtomtypes)
        for aType in self.atomTypes:
            aTypeName = aType.atomTypeName
            A = aType.ACOEF
            B = aType.BCOEF
            # one cannot infer sigma or epsilon for B = 0, assuming 0 for them
            if B == 0.0:
                sigma, epsilon, r0, epAmber = 0, 0, 0, 0
            else:
                r0 = 0.5 * math.pow((2*A/B), (1.0/6))
                epAmber = 0.25 * B*B/A
                sigma = 0.1 * math.pow((A/B), (1.0/6))
                epsilon = cal * epAmber
            line = " %-8s %-11s %3.5f  %3.5f   A   %13.5e %13.5e" % \
            (aTypeName, aTypeName, 0.0, 0.0, sigma, epsilon) + \
            " ; %4.2f  %1.4f\n" % (r0, epAmber)
            itpFile.write(line)

        itpFile.write(headMoleculetype % self.baseName)

        itpFile.write(headAtoms)
        qtot = 0.0
        for atom in self.atoms:
            id = self.atoms.index(atom) + 1
            aName = atom.atomName
            aType = atom.atomType.atomTypeName
            charge = atom.charge
            mass = atom.mass
            qtot += charge
            resnr = 1
            line = "%6d %4s %5d %5s %5s %4d %12.5f %12.5f ; qtot %1.3f\n" % \
            (id, aType,resnr, self.residueLabel, aName, id, charge, mass, qtot)
            itpFile.write(line)

        itpFile.write(headBonds)
        for bond in self.bonds:
            a1Name = bond.atoms[0].atomName
            a2Name = bond.atoms[1].atomName
            id1 = self.atoms.index(bond.atoms[0]) + 1
            id2 = self.atoms.index(bond.atoms[1]) + 1
            line = "%6i %6i %3i %13.4e %13.4e ; %6s-%6s\n" % (id1, id2, 1,
                   bond.rEq * 0.1, bond.kBond * 200 * cal, a1Name, a2Name)
            itpFile.write(line)

        itpFile.write(headPairs)
        for pair in self.atomPairs:
            a1Name = pair[0].atomName
            a2Name = pair[1].atomName
            id1 = self.atoms.index(pair[0]) + 1
            id2 = self.atoms.index(pair[1]) + 1
            line = "%6i %6i %6i ; %6s-%6s\n" % (id1, id2, 1, a1Name, a2Name)
            itpFile.write(line)

        itpFile.write(headAngles)
        for angle in self.angles:
            a1 = angle.atoms[0].atomName
            a2 = angle.atoms[1].atomName
            a3 = angle.atoms[2].atomName
            id1 = self.atoms.index(angle.atoms[0]) + 1
            id2 = self.atoms.index(angle.atoms[1]) + 1
            id3 = self.atoms.index(angle.atoms[2]) + 1
            line = "%6i %6i %6i %6i %13.4e %13.4e ; %6s-%6s-%6s\n" % (id1, id2,
            id3, 1, angle.thetaEq * 180/Pi, 2 * cal * angle.kTheta, a1, a2, a3)
            itpFile.write(line)

        itpFile.write(headProDih)
        self.setProperDihedralsCoefRB()
        for dih in self.properDihedralsCoefRB:
            a1 = dih[0][0].atomName
            a2 = dih[0][1].atomName
            a3 = dih[0][2].atomName
            a4 = dih[0][3].atomName
            id1 = self.atoms.index(dih[0][0]) + 1
            id2 = self.atoms.index(dih[0][1]) + 1
            id3 = self.atoms.index(dih[0][2]) + 1
            id4 = self.atoms.index(dih[0][3]) + 1
            c0, c1, c2, c3, c4, c5 = dih[1]
            line = \
            "%3i %3i %3i %3i %3i %10.5f %10.5f %10.5f %10.5f %10.5f %10.5f" %\
            (id1, id2, id3, id4, 3, c0, c1, c2, c3, c4, c5) \
            + " ; %6s-%6s-%6s-%6s\n" % (a1, a2, a3, a4)
            itpFile.write(line)

        itpFile.write(headImpDih)
        for dih in self.improperDihedrals:
            a1 = dih.atoms[0].atomName
            a2 = dih.atoms[1].atomName
            a3 = dih.atoms[2].atomName
            a4 = dih.atoms[3].atomName
            id1 = self.atoms.index(dih.atoms[0]) + 1
            id2 = self.atoms.index(dih.atoms[1]) + 1
            id3 = self.atoms.index(dih.atoms[2]) + 1
            id4 = self.atoms.index(dih.atoms[3]) + 1
            kd = dih.kPhi * cal
            pn = dih.period
            ph = dih.phase * 180/Pi
            line = "%3i %3i %3i %3i %3i %8.2f %9.5f %3i ; %6s-%6s-%6s-%6s\n" % \
                            (id1, id2, id3, id4, 1, ph, kd, pn, a1, a2, a3, a4)
            itpFile.write(line)

        print "Writing GROMACS GRO file\n"
        groFile.write(head % (gro, date))
        groFile.write(" %i\n" % len(self.atoms))
        for atom in self.atoms:
            coords = [c * 0.1 for c in atom.coords]
            line = "%5d%-4s%6s%5d%8.3f%8.3f%8.3f\n" % \
                   (1, self.residueLabel, atom.atomName,
                    self.atoms.index(atom)+1, coords[0], coords[1], coords[2])
            groFile.write(line)
        X = [a.coords[0] * 0.1 for a in self.atoms]
        Y = [a.coords[1] * 0.1 for a in self.atoms]
        Z = [a.coords[2] * 0.1 for a in self.atoms]
        boxX = max(X) - min(X) #+ 2.0 # 2.0 is double of rlist
        boxY = max(Y) - min(Y) #+ 2.0
        boxZ = max(Z) - min(Z) #+ 2.0
        groFile.write("%11.5f%11.5f%11.5f\n" % (boxX, boxY, boxZ))

        emMdp = \
"""
cpp                      = /usr/bin/cpp
define                   = -DFLEXIBLE
integrator               = steep
nsteps                   = 500
constraints              = none
emtol                    = 1000.0
emstep                   = 0.01
nstcomm                  = 1
ns_type                  = simple
nstlist                  = 0
rlist                    = 0
rcoulomb                 = 0
rvdw                     = 0
Tcoupl                   = no
Pcoupl                   = no
gen_vel                  = no
nstxout                  = 1
pbc                      = no
"""
        mdMdp = \
"""
cpp                      = /usr/bin/cpp
define                   = -DFLEXIBLE
integrator               = md
nsteps                   = 500
constraints              = none
emtol                    = 1000.0
emstep                   = 0.01
comm_mode                = angular
ns_type                  = simple
nstlist                  = 0
rlist                    = 0
rcoulomb                 = 0
rvdw                     = 0
Tcoupl                   = no
Pcoupl                   = no
gen_vel                  = no
nstxout                  = 1
pbc                      = no
"""
        emMdpFile = open('em.mdp', 'w')
        mdMdpFile = open('md.mdp', 'w')
        emMdpFile.write(emMdp)
        mdMdpFile.write(mdMdp)

    def writeCnsTopolFiles(self):
        autoAngleFlag = True
        autoDihFlag   = True
        cnsDir = os.path.abspath('.')

        pdb = self.baseName+'_NEW.pdb'
        par = self.baseName+'_CNS.par'
        top = self.baseName+'_CNS.top'
        inp = self.baseName+'_CNS.inp'

        pdbFileName = os.path.join(cnsDir, pdb)
        parFileName = os.path.join(cnsDir, par)
        topFileName = os.path.join(cnsDir, top)
        inpFileName = os.path.join(cnsDir, inp)

        self.CnsTopFileName = topFileName
        self.CnsInpFileName = inpFileName
        self.CnsParFileName = parFileName
        self.CnsPdbFileName = pdbFileName

        parFile = open(parFileName, 'w')
        topFile = open(topFileName, 'w')
        inpFile = open(inpFileName, 'w')

        print "Writing NEW PDB file\n"
        self.writePdb(pdbFileName)

        print "Writing CNS PAR file\n"
        parFile.write("Remarks " + head % (par, date))
        parFile.write("\nset echo=false end\n")

        parFile.write("\n{ Bonds: atomType1 atomType2 kb r0 }\n")
        lineSet = []
        for bond in self.bonds:
            a1Type = bond.atoms[0].atomType.atomTypeName
            a2Type = bond.atoms[1].atomType.atomTypeName
            kb = 1000.0
            if not self.allhdg:
                kb = bond.kBond
            r0 = bond.rEq
            line = "BOND %5s %5s %8.1f %8.4f\n" % (a1Type, a2Type, kb, r0)
            lineRev = "BOND %5s %5s %8.1f %8.4f\n" % (a2Type, a1Type, kb, r0)
            if line not in lineSet:
                if lineRev not in lineSet:
                    lineSet.append(line)
        for item in lineSet:
            parFile.write(item)

        parFile.write("\n{ Angles: aType1 aType2 aType3 kt t0 }\n")
        lineSet = []
        for angle in self.angles:
            a1 = angle.atoms[0].atomType.atomTypeName
            a2 = angle.atoms[1].atomType.atomTypeName
            a3 = angle.atoms[2].atomType.atomTypeName
            kt = 500.0
            if not self.allhdg:
                kt = angle.kTheta
            t0 = angle.thetaEq * 180/Pi
            line = "ANGLe %5s %5s %5s %8.1f %8.2f\n" % (a1, a2, a3, kt, t0)
            lineRev = "ANGLe %5s %5s %5s %8.1f %8.2f\n" % (a3, a2, a1, kt, t0)
            if line not in lineSet:
                if lineRev not in lineSet:
                    lineSet.append(line)
        for item in lineSet:
            parFile.write(item)

        parFile.write("\n{ Proper Dihedrals: aType1 aType2 aType3 aType4 kt per\
iod phase }\n")
        lineSet = set()
        for item in self.condensedProperDihedrals:
            seq = ''
            for dih in item:
                id = item.index(dih)
                l = len(item)
                a1 = dih.atoms[0].atomType.atomTypeName
                a2 = dih.atoms[1].atomType.atomTypeName
                a3 = dih.atoms[2].atomType.atomTypeName
                a4 = dih.atoms[3].atomType.atomTypeName
                kp = 750.0
                if not self.allhdg:
                    kp = dih.kPhi
                p = dih.period
                ph = dih.phase * 180/Pi
                if l > 1:
                    if id == 0:
                        line = "DIHEdral %5s %5s %5s %5s  MULT %1i %7.3f %4i %8\
.2f\n" % (a1, a2, a3, a4, l, kp, p, ph)
                    else:
                        line = "%s %7.3f %4i %8.2f\n" % (40*" ", kp, p, ph)
                else:
                    line = "DIHEdral %5s %5s %5s %5s %15.3f %4i %8.2f\n" % (a1,
                                                          a2, a3, a4, kp, p, ph)
                seq += line
            lineSet.add(seq)
        for item in lineSet:
            parFile.write(item)

        parFile.write("\n{ Improper Dihedrals: aType1 aType2 aType3 aType4 kt p\
eriod phase }\n")
        lineSet = set()
        for idh in self.improperDihedrals:
            a1 = idh.atoms[0].atomType.atomTypeName
            a2 = idh.atoms[1].atomType.atomTypeName
            a3 = idh.atoms[2].atomType.atomTypeName
            a4 = idh.atoms[3].atomType.atomTypeName
            kp = 750.0
            if not self.allhdg:
                kp = idh.kPhi
            p = idh.period
            ph = idh.phase * 180/Pi
            line = "IMPRoper %5s %5s %5s %5s %13.1f %4i %8.2f\n" % (a1, a2, a3,
                                                                 a4, kp, p, ph)
            lineSet.add(line)
        for item in lineSet:
            parFile.write(item)

        parFile.write("\n{ Nonbonded: Type Emin sigma; (1-4): Emin/2 sigma }\n")
        for at in self.atomTypes:
            A = at.ACOEF
            B = at.BCOEF
            atName = at.atomTypeName
            if B == 0.0:
                sigma, epAmber = 0, 0
            else:
                epAmber = 0.25 * B*B/A
                ep2 = epAmber/2.0
                sigma = math.pow((A/B), (1.0/6))
                sig2 = sigma
            line = "NONBonded %5s %11.6f %11.6f %11.6f %11.6f\n" % (atName,
                    epAmber, sigma, ep2, sig2)
            parFile.write(line)
        parFile.write("\nset echo=true end\n")

        print "Writing CNS TOP file\n"
        topFile.write("Remarks " + head % (top, date))
        topFile.write("\nset echo=false end\n")
        topFile.write("\nautogenerate angles=%s dihedrals=%s end\n" %
                      (autoAngleFlag, autoDihFlag))

        topFile.write("\n{ atomType  mass }\n")
        for at in self.atomTypes:
            atType = at.atomTypeName
            mass = at.mass
            line = "MASS %-5s %8.3f\n" % (atType, mass)
            topFile.write(line)

        topFile.write("\nRESIdue %s\n" % self.residueLabel)
        topFile.write("\nGROUP\n")

        topFile.write("\n{ atomName  atomType  Charge }\n")
        for at in self.atoms:
            atName = at.atomName
            atType = at.atomType.atomTypeName
            charge = at.charge
            line = "ATOM %-5s TYPE= %-5s CHARGE= %8.4f END\n" % (atName, atType,
                                                                 charge)
            topFile.write(line)

        topFile.write("\n{ Bonds: atomName1  atomName2 }\n")
        for bond in self.bonds:
            a1Name = bond.atoms[0].atomName
            a2Name = bond.atoms[1].atomName
            line = "BOND %-5s %-5s\n" % (a1Name, a2Name)
            topFile.write(line)

        if not autoAngleFlag:
            topFile.write("\n{ Angles: atomName1 atomName2 atomName3}\n")
            for angle in self.angles:
                a1Name = angle.atoms[0].atomName
                a2Name = angle.atoms[1].atomName
                a3Name = angle.atoms[2].atomName
                line = "ANGLe %-5s %-5s %-5s\n" % (a1Name, a2Name, a3Name)
                topFile.write(line)

        if not autoDihFlag:
            topFile.write("\n{ Proper Dihedrals: name1 name2 name3 name4 }\n")
            for item in self.condensedProperDihedrals:
                for dih in item:
                    l = len(item)
                    a1Name = dih.atoms[0].atomName
                    a2Name = dih.atoms[1].atomName
                    a3Name = dih.atoms[2].atomName
                    a4Name = dih.atoms[3].atomName
                    line = "DIHEdral %-5s %-5s %-5s %-5s\n" % (a1Name, a2Name,
                                                               a3Name, a4Name)
                    break
                topFile.write(line)

        topFile.write("\n{ Improper Dihedrals: aName1 aName2 aName3 aName4 }\n")
        for dih in self.improperDihedrals:
            a1Name = dih.atoms[0].atomName
            a2Name = dih.atoms[1].atomName
            a3Name = dih.atoms[2].atomName
            a4Name = dih.atoms[3].atomName
            line = "IMPRoper %-5s %-5s %-5s %-5s\n" % (a1Name, a2Name, a3Name,
                                                       a4Name)
            topFile.write(line)

        topFile.write("\nEND {RESIdue %s}\n" % self.residueLabel)

        topFile.write("\nset echo=true end\n")

        print "Writing CNS INP file\n"
        inpFile.write("Remarks " + head % (inp, date))
        inpData = \
"""
topology
  @%(CNS_top)s
end

parameters
  @%(CNS_par)s
  nbonds
      atom cdie shift eps=1.0  e14fac=0.4   tolerance=0.5
      cutnb=9.0 ctonnb=7.5 ctofnb=8.0
      nbxmod=5 vswitch wmin 1.0
  end
  remark dielectric constant eps set to 1.0
end

flags exclude elec ? end

segment name="    "
  chain
   coordinates @%(NEW_pdb)s
  end
end
coordinates @%(NEW_pdb)s

! Remarks If you want to shake up the coordinates a bit ...
 do (x=x+rand(10)-5) (all)
 do (y=y+rand(10)-5) (all)
 do (z=z+rand(10)-5) (all)
 write coordinates output=%(CNS_ran)s end

print threshold=0.02 bonds
print threshold=3.0 angles
print threshold=3.0 dihedrals
print threshold=3.0 impropers

Remarks Do Powell energy minimisation
minimise powell
  nstep=250 drop=40.0
end

write coordinates output=%(CNS_min)s end
write structure   output=%(CNS_psf)s end

! constraints interaction (not hydro) (not hydro) end

print threshold=0.02 bonds
print threshold=3.0 angles
print threshold=3.0 dihedrals
print threshold=3.0 impropers

flags exclude * include vdw end energy end
distance from=(not hydro) to=(not hydro) cutoff=2.6 end

stop
"""
        dictInp = {}
        dictInp['CNS_top'] = top
        dictInp['CNS_par'] = par
        dictInp['NEW_pdb'] = pdb
        dictInp['CNS_min'] = self.baseName+'_NEW_min.pdb'
        dictInp['CNS_psf'] = self.baseName+'_CNS.psf'
        dictInp['CNS_ran'] = self.baseName+'_rand.pdb'
        line = inpData % dictInp
        inpFile.write(line)

class Atom:
    """
        Charges in prmtop file has to be divide by 18.2223 to convert to charge
        in units of the electron charge.
        To convert ACOEF and BCOEF to r0 (Ang.) and epsilon (kcal/mol), as seen
        in gaff.dat for example; same atom type (i = j):
            r0 = 1/2 * (2 * ACOEF/BCOEF)^(1/6)
            epsilon = 1/(4 * A) * BCOEF^2
        To convert r0 and epsilon to ACOEF and BCOEF
            ACOEF = sqrt(ep_i * ep_j) * (r0_i + r0_j)^12
            BCOEF = 2 * sqrt(ep_i * ep_j) * (r0_i + r0_j)^6
                  = 2 * ACOEF/(r0_i + r0_j)^6
        where index i and j for atom types.
        Coord is given in Ang. and mass in Atomic Mass Unit.
    """
    def __init__(self, atomName, atomType, mass, charge, coord, ACOEF, BCOEF):
        self.atomName = atomName
        self.atomType = atomType
        self.mass = mass
        self.charge = charge / 18.2223
        self.coords = coord

class AtomType:
    """
        AtomType per atom in gaff or amber.
    """
    def __init__(self, atomTypeName, mass, ACOEF, BCOEF):
        self.atomTypeName = atomTypeName
        self.mass = mass
        self.ACOEF = ACOEF
        self.BCOEF = BCOEF

class Bond:
    """
        attributes: pair of Atoms, spring constant (kcal/mol), dist. eq. (Ang)
    """
    def __init__(self, atoms, kBond, rEq):
        self.atoms = atoms
        self.kBond = kBond
        self.rEq = rEq

class Angle:
    """
        attributes: 3 Atoms, spring constant (kcal/mol/rad^2), angle eq. (rad)
    """
    def __init__(self, atoms, kTheta, thetaEq):
        self.atoms = atoms
        self.kTheta = kTheta
        self.thetaEq = thetaEq # rad, to convert to degree: thetaEq * 180/Pi

class Dihedral:
    """
        attributes: 4 Atoms, spring constant (kcal/mol), periodicity,
        phase (rad)
    """
    def __init__(self, atoms, kPhi, period, phase):
        self.atoms = atoms
        self.kPhi = kPhi
        self.period = period
        self.phase = phase # rad, to convert to degree: kPhi * 180/Pi

if __name__ == '__main__':
    argsDict = parseArgs(sys.argv[1:])
    iF = argsDict.get('-i')
    cT = argsDict.get('-c', 'bcc')
    cV = argsDict.get('-n', None)
    mt = argsDict.get('-m', '1')
    at = argsDict.get('-a', 'gaff')
    ot = argsDict.get('-o', 'all')
    en = argsDict.get('-e', 'tleap')
    fs = False
    dg = False
    tt = False
    if '-f' in argsDict.keys(): fs = True
    if '-d' in argsDict.keys(): dg = True
    if '-t' in argsDict.keys(): tt = True

    molecule = ACTopol(iF, chargeType = cT, chargeVal = cV, debug = dg,
                       multiplicity = mt, atomType = at, force = fs,
                       outTopol = ot, engine = en, allhdg=tt)

    if not molecule.acExe:
        print "ERROR: no 'antechamber' executable... aborting!"
        sys.exit(1)

    if not molecule.babelExe:
        print "ERROR: no 'babel' executable... aborting!"
        sys.exit(1)

    #molecule.convertPdbToMol2()
    #print molecule.babelLog

    #molecule.execAntechamber()
    #print molecule.acLog

    #molecule.execSleap()
    #print molecule.sleapLog

    #molecule.execTleap()
    #print molecule.tleapLog, molecule.parmchkLog

    molecule.createACTopol()
    molecule.createMolTopol()
