set term png
set output '[% png_fname %]'

[% IF attachment_folder %]
cd '[% attachment_folder %]'
[% END %]

[% gnuplot_script %]
