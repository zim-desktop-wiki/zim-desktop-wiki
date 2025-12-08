
{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = [
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.python311Packages.dateparser
    pkgs.python311Packages.ics
    pkgs.python311Packages.attrs
    pkgs.python311Packages.pygobject3
  ];
}
