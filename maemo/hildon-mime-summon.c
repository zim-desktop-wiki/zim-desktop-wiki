/*
 * Copyright (C) 2007 Tuomas Kulve <tuomas@kulve.fi>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2, or (at your option)
 * any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 * 
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307,
 * USA.

gcc `pkg-config --cflags --libs libhildonmime glib-2.0 libosso` bz3688-loop.c -o with-loop


 */

#ifdef HAVE_CONFIG_H
#  include <config.h>
#endif

#include <stdio.h>
#include <libosso.h>
#include <hildon-mime.h>
#include <glib.h> 


int main(int argc, char *argv[])
{
  DBusConnection *dbus;
  osso_context_t *osso;
  GMainLoop* mainloop = NULL;

  int retval;
  
  if (argc != 2 && argc != 3) {
    fprintf(stderr, "Usage: %s [mimetype] file\n", argv[0]);
    return -1;
  }

  /* Initialize libosso */
  osso = osso_initialize("osso-mime-summon", "0.1", TRUE, NULL);
  if (osso == NULL) {
    fprintf(stderr, "Failed to initialize libosso\n");
    return -1;
  }

  dbus = (DBusConnection *) osso_get_dbus_connection(osso);
  if (dbus == NULL) {
    fprintf(stderr, "Failed to get dbus connection from osso context\n");
    return -1;
  }

  mainloop = g_main_loop_new(NULL, FALSE);
  if (mainloop == NULL) {
    /* Print error and terminate. */
    g_print("Couldn't create GMainLoop");
    return -1;
  }  

  if (argc == 2) {
	/* launch the file with automatic mime type detection */
	retval = hildon_mime_open_file(dbus, argv[1]);
	if (retval != 1) {
	  fprintf(stderr, "Failed to launch hildon_mime_open_file: %d\n", retval);
	  return -1;
	}
  } else {
	/* launch the file with given mime type */
	retval = hildon_mime_open_file_with_mime_type(dbus, argv[2], argv[1]);
	if (retval != 1) {
	  fprintf(stderr, 
			  "Failed to launch hildon_mime_open_file_with_mime_type: %d\n",
			  retval);
	  return -1;
	}
  }

  g_main_loop_run(mainloop);


  return 0;
}
