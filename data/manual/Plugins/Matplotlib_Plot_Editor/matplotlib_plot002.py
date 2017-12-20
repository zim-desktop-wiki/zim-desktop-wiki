import matplotlib.cbook as cbook

w, h = 512, 512

datafile = cbook.get_sample_data('ct.raw.gz', asfileobj=True)
s = datafile.read()
A = np.fromstring(s, np.uint16).astype(float)
A *= 1.0 / max(A)
A.shape = w, h

fig, (ax1,ax2) = plt.subplots(1,2,figsize=(10,5))
ax1.imshow(A)
ax1.axhline(h/2,color='w')
ax2.plot(A[h/2,:])