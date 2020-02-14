import sys
from struct import unpack
import numpy as np

class PulseWaves(object):
    '''
    Main class initiated with a PLS file (not PLZ).
    Generally, this is all you need to import:

    >>> from pulsewaves import PulseWaves
    >>> f = PulseWaves('sample.pls')
    '''
    def __init__(self, pls_file):
        if pls_file[-3:] != 'pls':
            sys.exit("error: reader assumes lower case file endings and only works for the uncompressed format (.pls).")

        with open(pls_file, 'rb') as f:
            #read header
            self.filename = pls_file
            self.file_sig = f.read(16).decode("utf-8").strip("\x00")
            if self.file_sig != 'PulseWavesPulse':
                sys.exit("error: %s is not in a valid pulse file format." % pls_file)
            self.global_params = unpack("=L", f.read(4))[0]
            self.file_id = unpack("=L", f.read(4))[0]
            self.proj_GUID1 = unpack("=L", f.read(4))[0]
            self.proj_GUID2 = unpack("H", f.read(2))[0]
            self.proj_GUID3 = unpack("H", f.read(2))[0]
            self.proj_GUID3 = unpack("B"*8, f.read(8))[0]
            self.sys_id = f.read(64).decode("utf-8").strip("\x00")
            self.software = f.read(64).decode("utf-8").strip("\x00")
            self.file_day = unpack("H", f.read(2))[0]
            self.file_year = unpack("H", f.read(2))[0]
            self.version_maj = unpack("B", f.read(1))[0]
            self.version_min = unpack("B", f.read(1))[0]
            self.header_size = unpack("H", f.read(2))[0]
            self.offset_to_pulses = unpack("q", f.read(8))[0]
            self.num_pulses = unpack("q", f.read(8))[0]
            self.pulse_format = unpack("=L", f.read(4))[0]
            self.pulse_attr = unpack("=L", f.read(4))[0]
            self.pulse_size = unpack("=L", f.read(4))[0]
            self.pulse_compression = unpack("=L", f.read(4))[0]
            self.reserved = unpack("q", f.read(8))[0]
            self.num_vlr = unpack("I", f.read(4))[0]
            self.num_avlr = unpack("!l", f.read(4))[0]
            self.t_scale  = unpack("d", f.read(8))[0]
            self.t_offset = unpack("d", f.read(8))[0]
            self.t_min = unpack("q", f.read(8))[0]
            self.t_max = unpack("q", f.read(8))[0]
            self.x_scale = unpack("d", f.read(8))[0]
            self.y_scale = unpack("d", f.read(8))[0]
            self.z_scale = unpack("d", f.read(8))[0]
            self.x_offset = unpack("d", f.read(8))[0]
            self.y_offset = unpack("d", f.read(8))[0]
            self.z_offset = unpack("d", f.read(8))[0]
            self.x_min = unpack("d", f.read(8))[0]
            self.x_max = unpack("d", f.read(8))[0]
            self.y_min = unpack("d", f.read(8))[0]
            self.y_max = unpack("d", f.read(8))[0]
            self.z_min = unpack("d", f.read(8))[0]
            self.z_max = unpack("d", f.read(8))[0]
            self.vlrs = {}
            self.avlrs = {}

            #read variable length records (VLR)
            for num_vlr in range(self.num_vlr):
                vlr = VLR(f)
                #if vlr is a scanner
                if  vlr.record_id >= 100001 and vlr.record_id < 100255:    
                    vlr.record = Scanner(f)

                #if vlr is a pulse descriptor 
                elif vlr.record_id >= 200001 and vlr.record_id < 200255:
                    #read pulse desciptor
                    vlr.record = PulseDecriptor(f)            
                    vlr.sampling_records = {}                
                
                    #read sampling record
                    for x in range(vlr.record.num_samplings):
                        vlr.sampling_records[x] = SamplingRecord(f)

                #if VLR not a scanner or pulse descriptor just read data but do not parse
                #TODO: add additional vlr types                        
                else:        
                    vlr.record = f.read(vlr.record_length).decode("utf-8").strip("\x00")
            
                #add vlr to the vlrs dictionary
                self.vlrs[vlr.record_id] = vlr

    def get_pulse(self, pulse_number):
        '''
        Returns a PulseRecord instance by pulse number.

        >>> from pulsewaves import PulseWaves
        >>> f = PulseWaves('sample.pls')
        >>> r = f.get_pulse(0)
        '''
        #check if pulse number if within range of expected number of pulse
        if pulse_number > self.num_pulses or pulse_number < 0:
            sys.exit("Pulse number outside the range of expected values")

        return PulseRecord(self, pulse_number)
                
    def get_waves(self, pulse_record):    
        '''
        Returns a Waves instance by pulse number.

        >>> from pulsewaves import PulseWaves
        >>> f = PulseWaves('sample.pls')
        >>> w = f.get_waves(0)
        '''
        #if a pulse number is given get the corresponding pulse record
        if type(pulse_record) == int:
            pulse_record = self.get_pulse(pulse_record)
        
        return Waves(self, pulse_record)

    def export(self, pulse_records = None, filename = None, compression = 'gzip'):
        '''
        Exports pulse records to an HDF5 file.

        >>> from pulsewaves import PulseWaves
        >>> f = PulseWaves('sample.pls')
        >>> f.export()
        '''
        import h5py
        from time import time
        t0 = time()

        if pulse_records is None:
            pulse_records = range(self.num_pulses)
            show_progress = True
        else:
            show_progress = False

        if filename is None:
            filename = self.filename[:-4] + '.hdf'

        #create the HDF5 file handle
        f = h5py.File(filename, 'w')
        c = f.create_dataset('XYZ', (1024, 3), maxshape = (None, 3), dtype = 'float64', compression = compression)
        a = f.create_dataset('Amplitude', (1024, 2), maxshape = (None, 2), dtype = 'int32', compression = compression)
        s = f.create_dataset('Index', (1024,), maxshape = (None,), dtype = 'uint32', compression = compression)

        #iterate through pulse records
        m = 0
        k = 0
        for i in pulse_records:
            if show_progress:
                dt = time() - t0
                sys.stdout.write('\b'*50+' %01d%% reading %05d pulse records per second' % (int(100 * i/self.num_pulses), int(i/dt)))
                sys.stdout.flush()

            r = PulseRecord(self, i)
            w = Waves(self, r)
            d = np.c_[w.segments[0], np.zeros(w.segments[0].shape[0])]
            for j in range(1, len(w.segments)):
                d = np.concatenate((d, np.c_[w.segments[j], j * np.ones(w.segments[j].shape[0])]))

            n = d.shape[0]
            if len(c) <= m+n:
                c.resize(m+n+1024, 0)
                a.resize(m+n+1024, 0)
                s.resize(m+n+1024, 0)

            c[m:m+n, :] = d[:, :3]
            a[m:m+n, :] = d[:, 3:].astype('int32')
            s[k] = m
            k += 1
            m += n

        s[k] = m
        s.resize(k+1, 0)
        c.resize(m, 0)
        a.resize(m, 0)
        f.close()
        if show_progress:
            sys.stdout.write('\b'*50+' 100%\n')

class PulseRecord(object):
    def __init__(self, header, pulse_number):
        with open(header.filename, 'rb') as f:
            #jump to the start of the pulse record
            f.seek(header.offset_to_pulses + pulse_number * header.pulse_size)
            self.gps_timestamp = header.t_scale * unpack("q", f.read(8))[0] + header.t_offset
            self.offset_to_waves = unpack("q", f.read(8))[0]
            self.x_anchor = header.x_scale * unpack("=l", f.read(4))[0] + header.x_offset
            self.y_anchor = header.y_scale * unpack("=l", f.read(4))[0] + header.y_offset
            self.z_anchor = header.z_scale * unpack("=l", f.read(4))[0] + header.z_offset
            self.x_target = header.x_scale * unpack("=l", f.read(4))[0] + header.x_offset
            self.y_target = header.y_scale * unpack("=l", f.read(4))[0] + header.y_offset
            self.z_target = header.z_scale * unpack("=l", f.read(4))[0] + header.z_offset
            self.first_return = unpack("h", f.read(2))[0]
            self.last_return = unpack("h", f.read(2))[0]
            self.pulse_number = pulse_number
            bits = []
            for bit in f.read(2):
                for i in range(8):
                    bits.append((bit >> i) & 1)
                                      
            self.pulse_descriptor = 200000 + int("".join(str(x) for x in bits[:8][::-1]),2)
            self.reserved = bits[8:12]
            self.edge = bits[12]
            self.scan_direction = bits[13]
            self.facet = bits[14:]
            self.intensity = unpack("B", f.read(1))[0]
            self.classification = unpack("B", f.read(1))[0]
        
        #calculate direction vector
        self.dx = (self.x_target - self.x_anchor)/1000
        self.dy = (self.y_target - self.y_anchor)/1000
        self.dz = (self.z_target - self.z_anchor)/1000

class Waves(object):
    def __init__(self, header, pulse_record):    
        #get sample records corresponding to the waveform
        descriptor = header.vlrs[pulse_record.pulse_descriptor]
        sample_records = descriptor.sampling_records

        #read header
        self.filename = header.filename[:-4] + '.wvs'
        with open(self.filename, 'rb') as f:
            self.file_sig = f.read(16).decode("utf-8").strip("\x00")
            self.compression = unpack("I", f.read(4))[0]
            self.reserved = unpack("B"*40, f.read(40))
            self.segments = {}
        
            #jump to the start of the wave
            f.seek(pulse_record.offset_to_waves)

            #cycle through each sample and segment
            key = 0
            for i in sample_records.keys():
                sample_record = sample_records[i]
                for j in range(sample_record.num_segments):
                    duration_anchor = unpack("=L", f.read(sample_record.bits_anchor//8))[0]
                    num_samples = unpack("=h", f.read(sample_record.bits_samples//8))[0]

                    samples = np.zeros((num_samples, 4))
                    for k in range(num_samples): 
                        samples[k, 3] = unpack("=h", f.read(sample_record.bits_per_sample//8))[0]
                        
                        #calculate 3 dimensional sample coordinates
                        samples[k, 0] = pulse_record.x_anchor + (duration_anchor + k) * pulse_record.dx
                        samples[k, 1] = pulse_record.y_anchor + (duration_anchor + k) * pulse_record.dy
                        samples[k, 2] = pulse_record.z_anchor + (duration_anchor + k) * pulse_record.dz
            
                    self.segments[key] = samples
                    key += 1

class VLR(object):
    def __init__(self, f):    
        self.user_id = f.read(16).decode("utf-8").strip("\x00").strip("\x00")
        self.record_id = unpack("I", f.read(4))[0]
        self.reserved =	unpack("I", f.read(4))[0]
        self.record_length = unpack("q", f.read(8))[0]
        self.desciption = f.read(64).decode("utf-8").strip("\x00").strip("\x00")

class Scanner(object):
    def __init__(self, f):  
        self.size = unpack("I", f.read(4))[0]
        self.reserved =	unpack("I", f.read(4))[0]
        self.instrument = f.read(64).decode("utf-8").strip("\x00").strip("\x00")
        self.serial = f.read(64).decode("utf-8").strip("\x00").strip("\x00")
        self.wavelength = unpack("f", f.read(4))[0]
        self.out_pulse_width = unpack("f", f.read(4))[0]
        self.scan_pattern = unpack("I", f.read(4))[0]
        self.num_facets = unpack("I", f.read(4))[0]
        self.scan_frequency = unpack("f", f.read(4))[0]	 
        self.scan_angle_min = unpack("f", f.read(4))[0]	 
        self.scan_angle_max = unpack("f", f.read(4))[0]	 
        self.pulse_frequency = unpack("f", f.read(4))[0] 
        self.beam_diam = unpack("f", f.read(4))[0]
        self.beam_diverge = unpack("f", f.read(4))[0]
        self.min_range = unpack("f", f.read(4))[0]
        self.max_range = unpack("f", f.read(4))[0]
        self.description = f.read(64).decode("utf-8").strip("\x00").strip("\x00")

class SamplingRecord(object):
    def __init__(self, f):     
        self.size = unpack("I", f.read(4))[0]
        self.reserved =	unpack("I", f.read(4))[0]
        sample_type = {1:"outgoing", 2:"returning"}
        self.type = sample_type[unpack("B", f.read(1))[0]]
        self.channel = unpack("B", f.read(1))[0]
        self.unused = unpack("B", f.read(1))[0]
        self.bits_anchor = unpack("B", f.read(1))[0]
        self.scale_anchor = unpack("f", f.read(4))[0]
        self.offset_anchor = unpack("f", f.read(4))[0]
        self.bits_segments = unpack("B", f.read(1))[0]
        self.bits_samples = unpack("B", f.read(1))[0]
        self.num_segments = unpack("H", f.read(2))[0]
        self.num_samples =  unpack("I", f.read(4))[0]
        self.bits_per_sample = unpack("H", f.read(2))[0]
        self.lut_index = unpack("H", f.read(2))[0]
        self.samples_units = unpack("f", f.read(4))[0]
        self.compression =  unpack("I", f.read(4))[0]
        self.description = f.read(64).decode("utf-8").strip("\x00").strip("\x00")   

class PulseDecriptor(object):
    def __init__(self, f):  
        self.size = unpack("I", f.read(4))[0]
        self.reserved =	unpack("I", f.read(4))[0]
        self.optical_center = unpack("=l", f.read(4))[0]
        self.num_extra_wave_bytes = unpack("H", f.read(2))[0]
        self.num_samplings = unpack("H", f.read(2))[0]
        self.sample_units = unpack("f", f.read(4))[0]
        self.compression = unpack("I", f.read(4))[0]
        self.scanner_index = unpack("I", f.read(4))[0]
        self.description = f.read(64).decode("utf-8").strip("\x00").strip("\x00")

