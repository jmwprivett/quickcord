// quickcord.app's executable: starts quicksend.pyw with the repo's venv Python.
//
// Python runs as a child rather than the app exec'ing into it, so macOS attributes the keyboard
// permission (Input Monitoring) to quickcord.app instead of to Python or Terminal.
// It also manages the Open at Login entry, which macOS ties to the app bundle that asks:
//   quickcord --login-item status|enable|disable
#import <Foundation/Foundation.h>
#import <ServiceManagement/ServiceManagement.h>
#include <signal.h>
#include <spawn.h>
#include <sys/wait.h>

extern char **environ;
static pid_t child;

static void forward(int sig) {
    if (child > 0) kill(child, sig);
}

static void alert(NSString *message) {
    CFUserNotificationDisplayNotice(0, kCFUserNotificationStopAlertLevel, NULL, NULL, NULL,
                                    CFSTR("quickcord can't start"), (__bridge CFStringRef)message, NULL);
}

static int login_item(const char *action) {
    SMAppService *service = SMAppService.mainAppService;
    NSError *error = nil;
    if (!strcmp(action, "status")) {
        puts(service.status == SMAppServiceStatusEnabled ? "enabled" : "disabled");
        return 0;
    }
    BOOL ok = !strcmp(action, "enable") ? [service registerAndReturnError:&error]
            : !strcmp(action, "disable") ? [service unregisterAndReturnError:&error] : NO;
    if (!ok) fprintf(stderr, "%s\n", error ? error.localizedDescription.UTF8String : "unknown action");
    return ok ? 0 : 1;
}

int main(int argc, char *argv[]) {
    @autoreleasepool {
        if (argc == 3 && !strcmp(argv[1], "--login-item")) return login_item(argv[2]);

        NSBundle *bundle = NSBundle.mainBundle;
        NSString *dir = [bundle objectForInfoDictionaryKey:@"QuickcordDir"];  // set by make_app.sh
        NSString *python = [dir stringByAppendingPathComponent:@".venv/bin/python"];
        NSString *script = [dir stringByAppendingPathComponent:@"quicksend.pyw"];
        if (![NSFileManager.defaultManager isExecutableFileAtPath:python] ||
            ![NSFileManager.defaultManager fileExistsAtPath:script]) {
            alert([NSString stringWithFormat:@"Couldn't find quickcord in %@. Run mac/make_app.sh again.", dir]);
            return 1;
        }

        // lets quicksend.pyw call back into this executable for --login-item
        setenv("QUICKCORD_APP", bundle.executablePath.fileSystemRepresentation, 1);
        signal(SIGTERM, forward);
        signal(SIGINT, forward);
        char *args[] = {(char *)python.fileSystemRepresentation, (char *)script.fileSystemRepresentation, NULL};
        int err = posix_spawn(&child, args[0], NULL, NULL, args, environ);
        if (err) {
            alert([NSString stringWithFormat:@"Couldn't run %@: %s", python, strerror(err)]);
            return 1;
        }
        int status;
        while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
        return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
    }
}
