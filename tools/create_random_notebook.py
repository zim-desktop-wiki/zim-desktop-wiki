#!/usr/bin/python

import sys
sys.path.insert(0, '.')

from zim.fs import Dir
from zim.notebook import Path, init_notebook, Notebook

LOREM_IPSUM = '''
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Mauris sodales facilisis est, ut posuere elit congue in. Nam aliquet posuere dui ut fermentum. Donec lobortis eros id pulvinar ultricies. Phasellus ligula leo, tristique in porta vel, aliquet sed magna. Nunc volutpat congue malesuada. Nulla dictum erat ut nisl fermentum porttitor. Suspendisse risus nisi, lacinia eu mattis eget, pretium sed odio. Cras faucibus dapibus dictum.

Pellentesque ut eleifend eros. Vivamus auctor tellus at ipsum posuere bibendum. In blandit arcu sed congue gravida. Mauris aliquet fermentum nunc in finibus. Proin cursus eu elit ac pellentesque. Suspendisse pharetra interdum neque aliquet suscipit. Phasellus lectus augue, fringilla ac vehicula eget, varius ac justo.

Sed finibus viverra leo, et ornare lectus finibus ut. Mauris ultricies lectus sed lorem faucibus iaculis. Suspendisse nec rutrum felis, at porttitor ipsum. Interdum et malesuada fames ac ante ipsum primis in faucibus. Curabitur lacinia libero ac turpis sagittis, eget imperdiet elit consectetur. Phasellus molestie sapien et lorem vestibulum luctus. Suspendisse dignissim tincidunt urna ac dictum. Phasellus nec pulvinar nibh. Pellentesque sit amet justo dapibus, varius nibh quis, pulvinar ante. Mauris cursus ex at enim gravida, in tristique arcu pharetra. Donec turpis enim, ullamcorper a urna in, aliquam pretium eros. Vivamus eleifend enim auctor metus euismod convallis. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Etiam vel sem elementum lorem viverra dapibus.

Sed consectetur mattis leo sit amet scelerisque. Maecenas nec hendrerit libero, nec convallis purus. Integer sed arcu et mauris lacinia condimentum eu eget arcu. Aenean tempor mauris at hendrerit sollicitudin. Praesent convallis orci ut justo euismod porta. Aenean molestie sollicitudin augue, a feugiat felis cursus eu. Proin condimentum libero sit amet commodo vehicula. Quisque imperdiet vel eros et viverra. Praesent id urna erat. Vivamus quis turpis gravida, eleifend nisl vel, pellentesque ante. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Integer tristique est convallis faucibus fermentum. Etiam pellentesque sem ut magna pellentesque, in commodo magna aliquet.

Sed augue metus, egestas eu magna tincidunt, aliquet varius arcu. Suspendisse posuere lectus at lacus gravida fermentum. Phasellus ut condimentum orci. Integer ut mauris ac urna consequat rutrum. Maecenas laoreet vel est ac varius. Sed ut libero blandit, convallis enim vel, pellentesque nulla. Phasellus odio nibh, fringilla sit amet auctor at, fringilla in purus. Duis ipsum metus, hendrerit efficitur consectetur non, finibus sed diam. Aenean quis dapibus diam, vitae condimentum mauris. Cum sociis natoque penatibus et magnis dis parturient montes, nascetur ridiculus mus.
'''


def flatlist(n_pages, template=LOREM_IPSUM):
    def pages_generator():
        for i in range(n_pages):
            yield Path('Page%i' % i), template

    return pages_generator()


def write_notebook(dir, pages):
    init_notebook(dir)
    notebook = Notebook.new_from_dir(dir)

    for path, content in pages:
        p = notebook.get_page(path)
        p.parse('wiki', content)
        notebook.store_page(p)
        print "Wrote", p.source.path


if __name__ == '__main__':
    path = sys.argv[1]
    dir = Dir(path)
    write_notebook(dir, flatlist(2000))
