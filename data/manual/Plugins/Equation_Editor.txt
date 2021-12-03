Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.4

====== Equation Editor ======

The equation editor is a simple dialog that allows you to insert equations into a page using **latex**.

**Dependencies:** This plugin requires a Latex suite to be installed as well as the "dvipng" application. In specific the "''latex''" and "''dvipng''" commands should be available in the system path. Additionally, if the dark mode preference is activated, the TeX package "xcolor" must be installed (included in most TeX distributions).

===== Preferences =====
* The option **Use font color for dark theme** sets an template variable to change the color scheme of the equations
* The option **Font size** sets the fonts size for the template in points
* The option **Equation image DPI** sets the DPI value with which the equation is generated as an images

===== Template =====
You can control the look of the equations using the special template "''plugins/equationeditor.tex''"". See [[Help:Templates]] for more information about template syntax.

There are variables that can be used in this template:
* "''equation''" which will be replaced with the content from the dialog
* "''dark_mode''" which allows the user to generate equations appropriate for dark mode themes and reflects the setting of the **Use font color for dark theme** preference setting
* "''font_size''" gives the value for the font size selected by the user in the preferences



===== Syntax =====

Some quick examples of the latex math syntax. For a complete reference see the links below:

{{./equation_01.png}}


'''
c = \sqrt{ a^2 + b^2 }

\int_{-\infty}^{\infty} \frac{1}{x} \, dx

f(x) = \sum_{n = 0}^{\infty} \alpha_n x^n

x_{1,2}=\frac{-b\pm\sqrt{\color{Red}b^2-4ac}}{2a}

\hat a  \bar b  \vec c  x'  \dot{x}  \ddot{x}
'''


===== References =====

* Micheal Downes, //Short Math Guide for LaTeX//, American Mathematical Society, 2002  [1]
* Tobias Oetiker e.a, //The Not So Short Introduction to LATEX2e//, 2007  [2]

* [1] http://www.ams.org/tex/amslatex.html
* [2] http://www.latex-project.org/guides/
* https://en.wikipedia.org/wiki/Help:Formula (latex parts only)
