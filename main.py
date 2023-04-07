import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('port', type=int, help='Port to listen on')
    parser.add_argument('language_code', type=str, help='Language code')
    parser.add_argument('speech_threshold', type=int, default=5000, nargs='?')
    parser.add_argument('speech_timeout', type=float, default=1, nargs='?')
    parser.add_argument('--device', type=str, default='', nargs='?')
    args = parser.parse_args()
    
    import runtime
    runtime.run(args)


if __name__ == '__main__':
    main()
