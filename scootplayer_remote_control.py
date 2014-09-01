#!/usr/bin/env python2.7

"""Remote control for multiple remote Scootplayer clients."""

import zmq
import random
import sys
import time
import cmd

class ScootplayerRemoteControl(cmd.Cmd):
    intro = 'Welcome to the Scootplayer Remote Control. Type help or ? to list commands.\n'
    prompt = '(scootplayer) '

    def do_start(self, arg):
        'Start playback on listening Scootplayers. Use given URL as MPD to download and play.'
        send_message('start', arg)

    def do_stop(self, _):
        'Stop playback on listening Scootplayers. Will terminate clients.'
        send_message('stop')

    def do_pause(self, _):
        'Pause playback on listening Scootplayers. Will NOT terminate clients.'
        send_message('pause')

    def do_resume(self, _):
        'Resume playback on listening Scootplayers. Can be used after a `pause` command.'
        send_message('resume')

    def do_exit(self, arg):
        'Exit the Scootplayer Remote Control.'
        print('Thank you for using the Scootplayer Remote Control.')
        return True

def send_message(action, url=''):
    socket.send("%s %s" % (action, url))

if __name__ == '__main__':
    try:
        port = sys.argv[1]
    except:
        port = "5556"
    print port
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind("tcp://*:%s" % port)
    ScootplayerRemoteControl().cmdloop()