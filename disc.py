import os, hashlib, struct, subprocess, fnmatch, shutil, urllib, array

import time
from title import *
from Crypto.Cipher import AES
from Struct import Struct

from common import *


class WOD: #WiiOpticalDisc
	class fsentry:
		name = ""
		type = 0
		parent = None
		offset = 0
		lenght = 0
		
		def __init__(self, name, type, parent, offset, len):
			self.name = ""
			if(parent != None):
				self.parent = parent
		def path(self):
			return parent.path() + "/" + name
			
	class fsdir(fsentry):
		def __init__(self, name, parent):
			fsentry.__init__(self, name, parent)
			
	class fsfile(fsentry):
		size = 0
		offset = 0
		
	class discHeader(Struct):
		__endian__ = Struct.BE
		def __format__(self):
			self.discId = Struct.string(1)
			self.gameCode = Struct.string(2)
			self.region = Struct.string(1)
			self.makerCode = Struct.uint8[2]
			self.h = Struct.uint8
			self.version = Struct.uint8
			self.audioStreaming = Struct.uint8
			self.streamingBufSize = Struct.uint8
			self.unused = Struct.uint8[14]
			self.magic = Struct.uint32
			self.title = Struct.string(64)
			self.hashVerify = Struct.uint8
			self.h3verify = Struct.uint8
		def __str__(self):
			ret = ''
			ret += '%s [%s%s%s]\n' % (self.title, self.discId, self.gameCode, self.region)
			if self.region == 'P':
				ret += 'Region : PAL\n'
			elif self.region == 'E':
				ret += 'Region : NTSC\n'
			elif self.region == 'J':
				ret += 'Region : JPN\n'
			ret += 'Version 0x%x Maker %i%i Audio streaming %x\n' % (self.version, self.makerCode[0], self.makerCode[1], self.audioStreaming)
			ret += 'Hash verify flag 0x%x H3 verify flag : 0x%x\n' % (self.hashVerify, self.h3verify)
			
			return ret
				
	# Many many thanks to Wiipower
	class Apploader(Struct):
		__endian__ = Struct.BE
		def __format__(self):
			self.buildDate = Struct.string(16)
			self.entryPoint = Struct.uint32
			self.size = Struct.uint32
			self.trailingSize = Struct.uint32
			self.padding = Struct.uint8[4]
		def __str__(self):
			ret = ''
			ret += 'Apploader built on %s\n' % self.buildDate
			ret += 'Entry point 0x%x\n' % self.entryPoint
			ret += 'Size %i (%i of them are trailing)\n' % (self.size, self.trailingSize)
			
			return ret
	
	def __str__(self):
		ret = ''
		ret += '%s\n' % self.discHdr
		ret += 'Found %i partitions (table at 0x%x)\n' % (self.partitionCount, self.partsTableOffset)
		ret += 'Found %i channels (table at 0x%x)\n' % (self.channelsCount, self.chansTableOffset)
		ret += '\n'
		ret += 'Partition %i opened (type 0x%x) at 0x%x\n' % (self.partitionOpen, self.partitionType, self.partitionOffset)
		ret += '%s' % self.partitionHdr
		ret += 'Partition key %s\n' % hexdump(self.partitionKey)
		ret += 'Tmd at 0x%x (%x)\n' % (self.tmdOffset, self.tmdSize)
		ret += 'main.dol at 0x%x (%x)\n' % (self.dolOffset, self.dolSize)
		ret += 'FST at 0x%x (%x)\n' % (self.fstSize, self.fstOffset)
		ret += '%s\n' % (self.appLdr)
		
		return ret
				
	def __init__(self, f):
		self.f = f
		self.fp = open(f, 'rb')
		
		self.discHdr = self.discHeader().unpack(self.fp.read(0x400))
		if self.discHdr.magic != 0x5D1C9EA3:
			raise Exception('Wrong disc magic')
					
		self.fp.seek(0x40000)
			
		self.partitionCount = 1 + struct.unpack(">I", self.fp.read(4))[0]
		self.partsTableOffset = struct.unpack(">I", self.fp.read(4))[0] << 2
		
		self.channelsCount = struct.unpack(">I", self.fp.read(4))[0]
		self.chansTableOffset = struct.unpack(">I", self.fp.read(4))[0] << 2
		
		self.partitionOpen = -1
		self.partitionOffset = -1
		self.partitionType = -1
		
	def decryptBlock(self, block):
		if len(block) != 0x8000:
			raise Exception('Block size too big/small')	
			
		blockIV = block[0x3d0:0x3dF + 1]
		print 'IV %s (len %i)\n' % (hexdump(blockIV), len(blockIV))
		blockData = block[0x0400:0x7FFF]
		
		return Crypto().decryptData(self.partitionKey, blockIV, blockData, True)
		
	def readPartition(self, offset, size):
		
		readStart = offset / 0x7C00
		readLen = (align(size, 0x7C00)) / 0x7C00
		blob = ''
		
		print 'Read at 0x%x (Start on %i block, ends at %i block) for %i bytes' % (offset, readStart, readStart + readLen, size)
		
		self.fp.seek(self.partitionOffset + 0x20000 + (0x8000 * readStart))
		if readLen == 0:
			blob += self.decryptBlock(self.fp.read(0x8000))
		else:
			for x in range(readLen + 1):
				blob += self.decryptBlock(self.fp.read(0x8000))
		
		print 'Read from 0x%x to 0x%x' % (offset, offset + size)
		offset -= readStart * 0x7C00
		return blob[offset:offset + size]
		
	def readUnencrypted(self, offset, size):
		if offset > 0x20000:
			raise Exception('This read is on encrypted data')
			
		# FIXMII : Needs testing, extracting the tmd cause to have 10 null bytes in the end instead of 10 useful bytes at start :|
		self.fp.seek(self.partitionOffset + 0x2A4 + offset)
		return self.fp.read(size)
		
	def parseFst(self, buffer):
		rootFiles = struct.unpack('>I', buffer[8:12])[0]
		namesTable = buffer[12 * (rootFiles):]
		
		open('tbl.bin', 'w+b').write(str(buffer[12 * (rootFiles):].split('\x00')))
	 
		for i in range(1, rootFiles):
			fstTableEntry = buffer[12 * i:12 * (i + 1)]
						
			if fstTableEntry[0] == '\x01':
				fileType = 1
			else:
				fileType = 0
			
			temp = struct.unpack('>I', fstTableEntry[0x0:0x4])[0]
			nameOffset = struct.unpack('>I', fstTableEntry[0x0:0x4])[0] & 0xffffff
			fileName = namesTable[nameOffset:nameOffset + 256].split('\x00')[0]
			print '%s %s\n' % (namesTable[nameOffset:nameOffset + 256].split('\x00')[0], namesTable[nameOffset:nameOffset + 256].split('\x00')[1])
			fileOffset = 4 * (struct.unpack('>I', fstTableEntry[0x4:0x8])[0])
			fileLenght = struct.unpack('>I', fstTableEntry[0x8:0x0c])[0]
			if fileName == '':
				time.sleep(5)			
			
			print '%s [%i] [0x%X] [0x%X] [0x%X]' % (fileName, fileType, fileOffset, fileLenght, nameOffset)
			
		os.chdir('..')

	def openPartition(self, index):
		if index > self.partitionCount:
			raise ValueError('Partition index too big')
			
		self.partitionOpen = index
		
		self.partitionOffset = self.partsTableOffset + (8 * self.partitionOpen)
		
		self.fp.seek(self.partsTableOffset + (8 * self.partitionOpen))
		
		self.partitionOffset = struct.unpack(">I", self.fp.read(4))[0] << 2
		self.partitionType = struct.unpack(">I", self.fp.read(4))[0]
		
		self.fp.seek(self.partitionOffset)
		
		self.tikData = self.fp.read(0x2A4)
		self.partitionKey = Ticket(self.tikData).getTitleKey()
		
		self.appLdr = self.Apploader().unpack(self.readPartition (0x2440, 32))
		self.partitionHdr = self.discHeader().unpack(self.readPartition (0x0, 0x400))

		self.fp.seek(self.partitionOffset + 0x2a4)

		self.tmdSize = struct.unpack(">I", self.fp.read(4))[0]
		self.tmdOffset = struct.unpack(">I", self.fp.read(4))[0] >> 2
		
		self.certsSize = struct.unpack(">I", self.fp.read(4))[0]
		self.certsOffset = struct.unpack(">I", self.fp.read(4))[0] >> 2
		
		self.H3TableOffset = struct.unpack(">I", self.fp.read(4))[0] >> 2
		
		self.dataOffset = struct.unpack(">I", self.fp.read(4))[0] >> 2
		self.dataSize = struct.unpack(">I", self.fp.read(4))[0] >> 2
		
		self.fstOffset = 4 * struct.unpack(">I", self.readPartition (0x424, 4))[0]
		self.fstSize = 4 * struct.unpack(">I", self.readPartition (0x428, 4))[0]
		
		self.dolOffset = 4 * struct.unpack(">I", self.readPartition (0x420, 4))[0]
		self.dolSize = self.fstOffset - self.dolOffset

	def getFst(self):
		fstBuf = self.readPartition(self.fstOffset, self.fstSize)
		self.parseFst(fstBuf)
		return fstBuf
		
	def getIsoBootmode(self):
		if self.discHdr.discId == 'R' or self.discHdr.discId == '_':
			return 2
		elif self.discHdr.discId == '0':
			return 1
		
	def getOpenedPartition(self):
		return self.partitionOpen
		
	def getOpenedPartitionOffset(self):
		return self.partitionOffset
		
	def getOpenedPartitionType(self):
		return self.partitionType
		
	def getPartitionsCount(self):
		return self.partitionCount
		
	def getChannelsCount(self):
		return self.channelsCount
		
	def getPartitionCerts(self):
		return self.readUnencrypted(self.certsOffset, self.certsSize)
		
	def getPartitionH3Table(self):
		return self.readUnencrypted(self.H3TableOffset, 0x18000)
		
	def getPartitionTmd(self):
		return self.readUnencrypted(self.tmdOffset, self.tmdSize)
		
	def getPartitionTik(self):
		self.fp.seek(self.partitionOffset)
		return self.fp.read(0x2A4)
		
	def getPartitionApploader(self):
		return self.readPartition (0x2440, self.appLdr.size + self.appLdr.trailingSize + 32)

	def extractPartition(self, index, fn = ""):

		if(fn == ""):
			fn = os.path.dirname(self.f) + "/" + os.path.basename(self.f).replace(".", "_") + "_out"
		try:
			origdir = os.getcwd()
			os.mkdir(fn)
		except:
			pass
		os.chdir(fn)
		
		self.fp.seek(0x18)
		if(struct.unpack(">I", self.fp.read(4))[0] != 0x5D1C9EA3):
			self.fp.seek(-4, 1)
			raise ValueError("Not a valid Wii Disc (GC not supported)! Magic: %08x" % struct.unpack(">I", self.fp.read(4))[0])

		self.fp.seek(partitionoffs)
		
		tikdata = self.fp.read(0x2A3)
		open("tik").write(tikdata)
		self.tik = Ticket("tik")
		self.titlekey = self.tik.getTitleKey()
		
		tmdsz = struct.unpack(">I", self.fp.read(4))[0]
		tmdoffs = struct.unpack(">I", self.fp.read(4))[0]
		
		certsz = struct.unpack(">I", self.fp.read(4))[0]
		certoffs = struct.unpack(">I", self.fp.read(4))[0]
		
		h3offs = struct.unpack(">I", self.fp.read(4))[0] << 2
		h3sz = 0x18000
		
		dataoffs = struct.unpack(">I", self.fp.read(4))[0] << 2
		datasz = struct.unpack(">I", self.fp.read(4))[0] << 2
		if(tmdoffs != self.fp.tell()):
			raise ValueError("TMD is in wrong place, something is fucked...wtf?")
		
		tmddata = self.fp.read(tmdsz)
		open("tmd").write(tmddata)
		
		self.tmd = TMD("tmd")
		
		
		print tmd.getIOSVersion()
		
		
		fst.seek(dataoffs)
		
		
		
		os.chdir("..")
	def _recurse(self, parent, names, recursion):		
		if(recursion == 0):
			pass	
		
		
