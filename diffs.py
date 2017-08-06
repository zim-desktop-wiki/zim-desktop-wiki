#!/bin/python2

#from pprint import pprint  
import difflib  
#import sys  
Debug = False 
#Debug = True 

def diff2files(fromfile, tofile):  
    '''Compare and merge linewise contents of 2 files, returning the merged text with conflicts dublicated
    '''  
    fromlines = open(fromfile, 'U').readlines()  
    tolines = open(tofile, 'U').readlines()  
    return diff2(fromlines, tolines)  

def diff2(fromlines, tolines):  
    '''Basic linewise diff of two lists of strings, returning the merged text with conflicts dublicated
    '''  
    diff = list(difflib.ndiff(fromlines, tolines))  
    dd = [ ln[2:] for ln in diff if ln[0] in [' ','+','-'] ]  
    return dd  

def unidiff2files(fromfile, tofile):  
    '''Compare and merge 2 files, return list of changes
    '''  
    fromlines = open(fromfile, 'U').readlines()  
    tolines = open(tofile, 'U').readlines()  
    return unidiff2(fromlines, tolines)  

def unidiff2(fromlines, tolines,fromfile='fromfile',tofile='tofile', nlines=0):  
    '''Compare and merge 2 files, return list of changes
    '''  
    output = list(difflib.unified_diff(fromlines, tolines, fromfile, tofile, n=nlines))
    #hunks = diffparse(output)
    if Debug:
        print(output)
    return output

def diff3files(fromfile, oldfile, tofile):  
    '''Compare and merge 3 files originating from a common ancestor. Return full merged text with any conflicts dublicated  
    '''  
    fromlines = open(fromfile, 'U').readlines()  
    tolines = open(tofile, 'U').readlines()  
    oldlines = open(oldfile, 'U').readlines()  
    return diff3(fromlines, oldlines, tolines)  

def diff3(fromlines, oldlines, tolines):  
    '''Poor man's 3-way diff+merge that compares linewise the changes in two lists of strings against a common  
    ancestor, keeping common and nonconflicting changes and dublicating conflicts. Returns full merged output
    '''  
    diff1 = list(difflib.ndiff(oldlines, tolines))  
    diff1 = [ x for x in diff1 if x[0] in [' ', '+'] ]
    diff2 = list(difflib.ndiff(oldlines, fromlines))  
    diff2 = [ x for x in diff2 if x[0] in [' ', '+'] ]
    diff = list(difflib.ndiff(list(diff1), list(diff2)))  
    

    if Debug:
        print('\tINPUt')
        print('fromlines')
        print(''.join(fromlines))
        print('oldlines')
        print(''.join(oldlines))
        print('tolines')
        print(''.join(tolines))
        print('\tDIFFS')
        print('old-to')
        print(''.join(diff1))
        print('old-from')
        print(''.join(diff2))
        print('3-way simple')
        print(''.join([ln[4:] for ln in list(diff) if ((ln[0]==' ' and ln[2] in [' ','+']) or (ln[0] in ['+','-'] and ln[2] in ['+'])) ]))

    return [ln[4:] for ln in list(diff) if ((ln[0]==' ' and ln[2] in [' ','+']) or (ln[0] in ['+','-'] and ln[2] in ['+'])) ]  

def unidiff3files(fromfile, oldfile, tofile):  
    '''Compare and merge 3 files originating from a common ancestor. Any conflicts will be dublicated, output as list of changes
    to convert fromfiles to fully merged text
    '''  
    fromlines = open(fromfile, 'U').readlines()  
    tolines = open(tofile, 'U').readlines()  
    oldlines = open(oldfile, 'U').readlines()
    
    return unidiff3(fromlines, oldlines, tolines)  

def unidiff3(fromlines, oldlines, tolines, fromfile='fromfile', tofile='tofile', nlines=0):  
    '''Poor man's 3-way diff+merge that compares linewise the changes in two lists of strings agains a common  
    ancestor, keeping common and nonconflicting changes and dublicating conflicts. Output as list of changes to
    convert fromlines to fully merged text
    '''  
    
    output = diff3(fromlines,oldlines,tolines)
    output = list(difflib.unified_diff(fromlines, output, fromfile,tofile,n=nlines))

    #hunks = diffparse(output)
    
    if Debug:
        print('full diff:')
        print('\t'.join(output))
        print(''.join(output))
    return output

def diffparse(input):
    '''Parse unified diff format input into a list of changes with each hunk presented as element [line1#, #changes, line2#, # changes, [deletions], [additions]]
    '''
    hunks = []
    for s in input[2:]: #only single file, start after +++ and ---
        if s[0] == '@':
            hunks.append([])
            linedata = s[3:-3].split(' ')
            fromlinedata = linedata[0].split(',')
            tolinedata = linedata[1].split(',')
            hunks[-1].append(fromlinedata[0].strip('-'))
            if len(fromlinedata)>1:
                hunks[-1].append(fromlinedata[1])
            else:
                hunks[-1].append('1')
            hunks[-1].append(tolinedata[0].strip('+'))
            if len(tolinedata)>1:
                hunks[-1].append(tolinedata[1])
            else:
                hunks[-1].append('1')
#            hunks[-1].append(linedata[1].split(',')[-1])
            hunks[-1].append([])
            hunks[-1].append([])
#            toline[hunk] = s[9]
#            tolinesnb[hunk] = s[11]
        elif s[0] in ['-']:
            hunks[-1][-2].append(s[1:])
        elif s[0] in ['+']:
            hunks[-1][-1].append(s[1:])

    return hunks


if __name__ == '__main__':  
    import sys  
    usage = "usage: %prog file1 oldfile file2 or %prog file1 file2"  
    help='Poor man 3-way diff'  

    args = sys.argv[1:]

    if len(args) < 2 or len(args)>3:  
        print(help)  
        print(usage)  
        sys.exit(1)  

    if len(args) == 3:  
        fromfile, oldfile, tofile = args # as specified in the usage string  
        #dd=diff3files(fromfile, oldfile, tofile)  
        dd=unidiff3files(fromfile, oldfile, tofile)  
    elif len(args) ==2:  
        fromfile, tofile = args # as specified in the usage string  
        #dd=diff2files(fromfile, tofile)  
        dd=unidiff2files(fromfile, tofile)  
    try:
        sys.stdout.writelines(dd)
    except:
        print('dd')
        print(dd)
        for k in reversed(range(len(dd))):
            print(dd[k][0])

