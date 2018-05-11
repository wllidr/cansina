import threading
import time
import sys
import urllib
import hashlib

import requests

unuseful_codes = ['404']
strict_codes = ['100', '200', '300', '301', '302', '401', '403', '405', '500']


class Visitor(threading.Thread):
    auth = None
    user_agent = None
    proxy = None
    discriminator = None
    banned_location = None
    banned_md5 = None
    delay = None
    requests = ""
    size_discriminator = -1
    killed = False
    cookies = None
    persist = False
    allow_redirects = False

    @staticmethod
    def allow_redirects(pref):
        Visitor.allow_redirects = pref

    @staticmethod
    def kill():
        Visitor.killed = True

    @staticmethod
    def set_discriminator(discriminator):
        Visitor.discriminator = discriminator

    @staticmethod
    def set_cookies(_cookies):
        Visitor.cookies = _cookies

    @staticmethod
    def set_size_discriminator(size_discriminator):
        if size_discriminator:
            Visitor.size_discriminator = [int(x) for x in size_discriminator.split(",")]
        else:
            Visitor.size_discriminator = []

    @staticmethod
    def set_banned_location(banned_location):
        Visitor.banned_location = banned_location

    @staticmethod
    def set_banned_md5(banned_md5):
        Visitor.banned_md5 = banned_md5

    @staticmethod
    def set_user_agent(useragent):
        Visitor.user_agent = useragent

    @staticmethod
    def set_proxy(proxy):
        Visitor.proxy = proxy

    @staticmethod
    def set_delay(delay):
        Visitor.delay = float(delay)

    @staticmethod
    def set_requests(type_request):
        Visitor.requests = type_request

    @staticmethod
    def set_authentication(auth):
        Visitor.auth = tuple(auth.split(':')) if auth else auth

    @staticmethod
    def set_persist(persist):
        Visitor.persist = persist

    def __init__(self, visitor_id, payload, results):
        threading.Thread.__init__(self)
        self.visitor_id = visitor_id
        self.payload = payload
        self.results = results.get_results_queue()
        self.__time = []
        self.session = None

    def run(self):
        try:
            while not self.payload.empty():
                if Visitor.killed:
                    break
                self.visit(self.payload.get())
                self.payload.task_done()
        except:
            pass

    def visit(self, task):
        def _dumb_redirect(url):
            origin = "{0}{1}".format(task.target, task.resource)

            # Detect redirect to same page but ended with slash
            if url == origin:
                return True
            if url == origin + '/':
                return True

            # Detect redirect to root
            if url == task.target:
                return True

            return False

        try:
            headers = {}
            if Visitor.user_agent:
                headers = {"user-agent": Visitor.user_agent}

            now = time.time()
            timeout = sum(self.__time) / len(self.__time) if self.__time else 10

            # Persistent connections
            if Visitor.persist:
                if not self.session:
                    self.session = requests.Session()
            else:
                self.session = requests

            r = None
            if Visitor.proxy:
                if Visitor.requests == "GET":
                    r = self.session.get(task.get_complete_target(),
                                         headers=headers,
                                         proxies=Visitor.proxy,
                                         verify=False,
                                         timeout=timeout,
                                         auth=Visitor.auth,
                                         cookies=Visitor.cookies,
                                         allow_redirects=Visitor.allow_redirects)

                elif Visitor.requests == "HEAD":
                    r = self.session.head(task.get_complete_target(),
                                          headers=headers,
                                          proxies=Visitor.proxy,
                                          verify=False,
                                          timeout=timeout,
                                          auth=Visitor.auth,
                                          cookies=Visitor.cookies,
                                          allow_redirects=Visitor.allow_redirects)
            else:
                if Visitor.requests == "GET":
                    r = self.session.get(task.get_complete_target(),
                                         headers=headers,
                                         verify=False,
                                         timeout=timeout,
                                         auth=Visitor.auth,
                                         cookies=Visitor.cookies,
                                         allow_redirects=Visitor.allow_redirects)

                elif Visitor.requests == "HEAD":
                    r = self.session.head(task.get_complete_target(),
                                          headers=headers,
                                          verify=False,
                                          timeout=timeout,
                                          auth=Visitor.auth,
                                          cookies=Visitor.cookies,
                                          allow_redirects=Visitor.allow_redirects)

            after = time.time()
            delta = (after - now) * 1000
            tmp_content = r.content
            task.response_size = len(tmp_content)
            task.response_time = delta
            self.__time.append(delta)

            # If discriminator is found we mark it 404
            if sys.version_info[0] >= 3:
                tmp_content = tmp_content.decode('UTF-8')
            if Visitor.discriminator and Visitor.discriminator in tmp_content:
                r.status_code = '404'

            if Visitor.banned_md5 and hashlib.md5("".join(tmp_content)).hexdigest() == self.banned_md5:
                r.status_code = '404'

            # Check if page size is not what we need
            if task.response_size in Visitor.size_discriminator:
                r.status_code = '404'

            task.set_response_code(r.status_code)

            # Look for interesting content
            if task.content and (task.content in tmp_content) and not task.response_code == '404':
                task.content_has_detected(True)

            # Look for a redirection
            if Visitor.allow_redirects:
                if len(r.history) > 0 and not _dumb_redirect(r.history[-1].url):
                    task.response_code = str(r.history[0].status_code)
                    task.location = r.history[-1].url
            else:
                if str(r.status_code).startswith('3'):
                    task.set_response_code('404')

            if 'content-type' in [h.lower() for h in r.headers.keys()]:
                try:
                    task.response_type = r.headers['Content-Type'].split(';')[0]
                except:
                    pass

            self.results.put(task)

            if Visitor.delay:
                time.sleep(Visitor.delay)

        except (requests.ConnectionError, requests.Timeout) as e:
            # sys.stderr.write("Connection (or/and) timeout error" + os.linesep)
            # TODO log to a file instead of screen
            print ("[!] Timeout/Connection error")
            print (e)

        except Exception as e:
            print ("[!] General exception while visiting")
            print (e)
