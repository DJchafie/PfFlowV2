from datetime import date, datetime

import napalm
from DynamicQoS.settings import MEDIA_ROOT
from django.db import models
# Create your models here.
from jinja2 import Environment, FileSystemLoader
from napalm import get_network_driver
from netaddr import *
from netmiko import ConnectHandler
from .validator import *


class Topology(models.Model):
    topology_name = models.CharField(max_length=255)
    topology_desc = models.CharField(max_length=255)

    def __str__(self):
        return self.topology_name


class BusinessType(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class BusinessApp(models.Model):
    name = models.CharField(max_length=255)
    business_type = models.ForeignKey(BusinessType, on_delete=models.CASCADE, null=True)
    match = models.CharField(max_length=255)
    recommended_dscp = models.CharField(max_length=255)
    delay_ref = models.IntegerField()
    loss_ref = models.IntegerField()

    @property
    def priority(self):
        if self.recommended_dscp.startswith("a"):
            return self.recommended_dscp[2]

    @property
    def drop(self):
        if self.recommended_dscp.startswith("a"):
            return self.recommended_dscp[3]

    @property
    def __str__(self):
        return self.name


class Policy(models.Model):
    name = models.CharField(max_length=255, unique=True, error_messages={'unique': 'this name is in used'})
    description = models.CharField(max_length=255)
    enable = models.BooleanField(default=False)
    deploy = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class PolicyIn(models.Model):
    policy_ref = models.ForeignKey(Policy, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return self.name

    @property
    def name(self):
        return self.policy_ref.name

    @property
    def description(self):
        return self.policy_ref.description

    @property
    def render_policy(self):
        env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        classes = Application.objects.filter(policy_in_id=self.id)
        named = env.get_template("policyIn.j2")
        config_file = named.render(classes=classes, a=self)
        config = config_file.splitlines()
        return config_file

    @property
    def render_no_policy(self):
        env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        classes = Application.objects.filter(policy_in_id=self.id)
        named = env.get_template("no_policyIn.j2")
        config_file = named.render(classes=classes, a=self)
        config = config_file.splitlines()
        # driver = napalm.get_network_driver('ios')
        # device = driver(hostname='192.168.5.1', username='admin',
        #                 password='admin')
        #
        # print('Opening ...')
        # device.open()
        # print('Loading replacement candidate ...')
        # device.load_merge_candidate(config=config_file)
        # print('\nDiff:')
        # print(device.compare_config())
        # print('Committing ...')

        return config_file

    @property
    def remove_applications(self):
        apps = Application.objects.filter(policy_in=self)
        env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        output = env.get_template("remove_applications.j2")
        config_file = output.render(applications=apps)
        return config_file

    @property
    def add_applications(self):
        apps = Application.objects.filter(policy_in=self)
        env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        output = env.get_template("add_applications.j2")
        config_file = output.render(applications=apps)
        return config_file


class PolicyOut(models.Model):
    policy_ref = models.ForeignKey(Policy, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return self.name

    @property
    def name(self):
        # interface = Interface.objects.get(policy_out_ref=self)
        interfaces = Interface.objects.all()
        for i in interfaces:
            if i.policy_out_ref == self:
                return "OUT_{}_{}".format(self.policy_ref.name, i.interface_name)

    @property
    def description(self):
        return self.policy_ref.description

    @property
    def render_policy(self):
        env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        groups = Group.objects.filter(policy=self.policy_ref)
        regroupement_classes = RegroupementClass.objects.filter(policy_out_id=self.id)
        dscp_list = Dscp.objects.all()
        classes = Application.objects.all()
        named = env.get_template("policyOut.j2")
        config_file = named.render(groups=groups, classes=classes, a=self, regroupement_classes=regroupement_classes,
                                   dscp_list=dscp_list)
        return config_file

    @property
    def render_no_policy(self):
        env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        groups = Group.objects.filter(policy=self.policy_ref)
        named = env.get_template("no_policyOut.j2")
        config_file = named.render(groups=groups, a=self)
        return config_file

    @property
    def service_policy(self):
        interface = Interface.objects.get(policy_out_ref=self)
        env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        output = env.get_template("service_policy.j2")
        config_file = output.render(interface=interface)
        return config_file


class Policing(models.Model):
    cir = models.CharField(max_length=255)
    pir = models.CharField(max_length=255)
    dscp_transmit = models.CharField(max_length=255)


class Shaping(models.Model):
    peak = models.CharField(max_length=255)
    average = models.CharField(max_length=255)


class Group(models.Model):
    name = models.CharField(max_length=255)
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, null=True)
    priority = models.CharField(max_length=255)

    @property
    def all_applications(self):
        return len(Application.objects.filter(group=self))

    @property
    def list_applications(self):
        return Application.objects.filter(group=self)


class RegroupementClass(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True)
    policing = models.ForeignKey(Policing, on_delete=models.CASCADE, null=True)
    shaping = models.ForeignKey(Shaping, on_delete=models.CASCADE, null=True)
    policy_out = models.ForeignKey(PolicyOut, on_delete=models.CASCADE, null=True)
    bandwidth = models.CharField(max_length=255)
    priority = models.CharField(max_length=255)
    bits = models.IntegerField(null=True)

    def __str__(self):
        return self.name

    @property
    def name(self):
        return self.group.name

    @property
    def oppressed_tos(self):
        oppressed = None
        v = 0
        dscps = Dscp.objects.filter(regroupement_class=self)
        for tos in dscps:
            if tos.delay_ratio >= 2 or tos.loss_ratio >= 2:
                if tos.c_ratio > v:
                    v = tos.c_ratio
                    oppressed = tos

        return oppressed

    @property
    def excessive_tos(self):
        excessive = None
        v = 0
        dscps = Dscp.objects.filter(regroupement_class=self)
        for tos in dscps:
            if tos.ratio >= v:
                v = tos.ratio
                excessive = tos

        return excessive


class Dscp(models.Model):
    dscp_value = models.CharField(max_length=255)
    regroupement_class = models.ForeignKey(RegroupementClass, on_delete=models.CASCADE, null=True)
    drop_min = models.CharField(max_length=255)
    drop_max = models.CharField(max_length=255)
    denominator = models.CharField(max_length=255)
    drop_min_old = models.CharField(max_length=255)
    drop_max_old = models.CharField(max_length=255)
    drop_min_new = models.CharField(max_length=255)
    drop_max_new = models.CharField(max_length=255)
    delay = models.IntegerField(null=True, default=400)
    loss = models.IntegerField(null=True, default=20)
    ratio = models.IntegerField(null=True, default=40)

    @property
    def delay_ref(self):
        apps = Application.objects.filter(mark=self.dscp_value)
        delays = []
        for app in apps:
            delays.append(app.business_app.delay_ref)
        if len(delays) == 0:
            return self.delay
        else:
            return min(delays)

    @property
    def loss_ref(self):
        apps = Application.objects.filter(mark=self.dscp_value)
        delays = []
        for app in apps:
            delays.append(app.business_app.loss_ref)
        if len(delays) == 0:
            return self.loss
        else:
            return min(delays)

    @property
    def delay_ratio(self):
        return round(self.delay / self.delay_ref)

    @property
    def loss_ratio(self):
        return round(self.loss / self.loss_ref)

    @property
    def c_ratio(self):
        if self.dscp_value != "EF":
            c = int(self.dscp_value[3])
            return c * max(self.delay_ratio, self.loss_ratio)
        else:
            return 0


class Application(models.Model):
    RECOMMENDED, CS6, EF, CS5, AF43, AF42, AF41, CS4, AF33, \
    AF32, AF31, CS3, AF23, AF22, AF21, CS2, AF13, AF12, \
    AF11, CS1, DEFAULT = "RECOMMENDED", "CS6", "EF", "CS5", "AF43", "AF42", "AF41", "CS4", "AF33", \
                         "AF32", "AF31", "CS3", "AF23", "AF22", "AF21", "CS2", "AF13", "AF12", "AF11", "CS1", "DEFAULT"
    DSCP = (
        (RECOMMENDED, "RECOMMENDED"),
        (CS6, "CS6"),
        (EF, "EF"),
        (CS5, "CS5"),
        (AF43, "AF43"),
        (AF42, "AF42"),
        (AF41, "AF41"),
        (CS4, "CS4"),
        (AF33, "AF33"),
        (AF32, "AF32"),
        (AF31, "AF31"),
        (CS3, "CS3"),
        (AF23, "AF23"),
        (AF22, "AF22"),
        (AF21, "AF21"),
        (CS2, "CS2"),
        (AF13, "AF13"),
        (AF12, "AF12"),
        (AF11, "AF11"),
        (CS1, "CS1"),
        (DEFAULT, "DEFAULT"),
    )

    IP, TCP, UDP = "ip", "tcp", "udp"
    PROTOCOL = (
        (IP, "ip"),
        (TCP, "tcp"),
        (UDP, "udp"),
    )

    business_type = models.ForeignKey(BusinessType, on_delete=models.CASCADE, null=True)
    business_app = models.ForeignKey(BusinessApp, on_delete=models.CASCADE, null=True)
    policy_in = models.ForeignKey(PolicyIn, on_delete=models.CASCADE, null=True)
    mark = models.CharField(max_length=20, choices=DSCP,default=RECOMMENDED)
    dscp = models.ForeignKey(Dscp, on_delete=models.CASCADE, null=True)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True)
    source = models.CharField(max_length=255, null=True)
    destination = models.CharField(max_length=255, null=True)
    begin_time = models.CharField(max_length=255, null=True)
    end_time = models.CharField(max_length=255, null=True)
    protocol_type = models.CharField(max_length=255, choices=PROTOCOL, default=IP)
    port_number = models.CharField(max_length=255)
    custom_name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

    @property
    def name(self):
        if self.business_app is not None:
            return "{}".format(self.business_app.name)
        if self.custom_name is not None:
            return self.custom_name

    @property
    def category(self):
        if self.business_app is not None:
            return "{}".format(self.business_type.name)
        if self.custom_name is not None:
            return "custom"

    @property
    def match(self):
        if self.business_app is not None:
            return "{}".format(self.business_app.match)
        else:
            return None

    @property
    def dscp_value(self):
        if self.mark != '':
            return self.mark
        else:
            return self.business_app.recommended_dscp

    @property
    def app_priority(self):
        if self.mark.startswith("A"):
            return self.mark[2]
        elif self.business_app is not None:
            return self.business_app.priority
        else:
            return None

    @property
    def drop_prob(self):
        if self.mark.startswith("A"):
            return self.mark[3]
        elif self.business_app is not None:
            return self.business_app.drop
        else:
            return None

    @property
    def time_range(self):
        if self.begin_time != '':
            if self.end_time != '':
                return "{}_time_range".format(self.name)
        else:
            return None

    @property
    def acl_name(self):
        return "{}_acl".format(self.name)

    @property
    def render_time_range(self):
        env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        output = env.get_template("time.j2")
        config_file = output.render(a=self)

        return config_file

    @property
    def render_no_acl(self):
        env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        output = env.get_template("no_acl.j2")
        config_file = output.render(a=self)

        return config_file

    @property
    def acl_list(self):
        source = ''
        source_wild_card = ''
        destination = ''
        destination_wild_card = ''
        if self.source != 'any':
            source = IPNetwork(self.source)
            source_wild_card = source.hostmask.ipv4()
        if self.destination != 'any':
            destination = IPNetwork(self.destination)
            destination_wild_card = destination.hostmask.ipv4()

        env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        output = env.get_template("acl.j2")
        config_file = output.render(source_wild_card=source_wild_card,
                                    destination_wild_card=destination_wild_card,
                                    source=source,
                                    destination=destination,
                                    a=self)

        return config_file


class Access(models.Model):
    management_interface = models.CharField(max_length=255)
    management_address = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    enable_secret = models.CharField(max_length=255)


class Device(models.Model):
    hostname = models.CharField(max_length=255)
    management = models.ForeignKey(Access, on_delete=models.CASCADE, null=True)
    topology_ref = models.ForeignKey(Topology, on_delete=models.CASCADE, null=True)
    policy_ref = models.ForeignKey(Policy, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.hostname

    def username(self):
        return self.management.username

    def password(self):
        return self.management.password

    def address(self):
        return self.management.management_address

    def enable(self):
        return self.management.enable_secret

    def netmiko_connect(self):
        return ConnectHandler(device_type="cisco_ios", ip=self.management.management_address,
                              username=self.management.username, password=self.management.password)

    def connect(self):
        driver = get_network_driver("ios")
        device = None
        try:
            device = driver(self.management.management_address, self.management.username,
                            self.management.password, timeout=180)
            device.open()
        except Exception as e:
            print(e)
        return device

    def enable_nbar(self):
        interfaces = Interface.objects.filter(device_ref=self)
        env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        output = env.get_template("protocol_discovery.j2")
        config_file = output.render(interfaces=interfaces)
        connection = self.connect()
        try:
            connection.load_merge_candidate(config=config_file)
            connection.commit_config()
            connection.close()
            return True
        except Exception as e:
            print(e)
            connection.close()
            return False

    def discovery_application(self):
        list_app = []
        interfaces = Interface.objects.filter(device_ref=self)
        connection = self.netmiko_connect()
        print("opening......")
        for interface in interfaces:
            try:
                cmd = "show ip nbar protocol-discovery interface " + interface.interface_name

                file = connection.send_command(
                    "show ip nbar protocol-discovery interface " + interface.interface_name).splitlines()

                p = False
                for line in file:
                    if p or "-------------------" in line:
                        p = True

                        k = line.split()
                        for a in k:
                            if a.isdigit():
                                break
                            if "----" in a:
                                break
                            if "unknown" in a:
                                break
                            if "Total" in a:
                                break
                            else:
                                list_app.append(a)
            except Exception as e:
                print(e)
        return list_app

    def ingress(self):
        interfaces = Interface.objects.filter(ingress=True, device_ref=self)
        if interfaces is not None:
            return True
        else:
            return False

    def egress(self):
        interfaces = Interface.objects.filter(egress=True, device_ref=self)
        if interfaces is not None:
            return True
        else:
            return False

    def wan(self):
        interfaces = Interface.objects.filter(wan=True, device_ref=self)
        if interfaces is not None:
            return True
        else:
            return False

    def service_policy(self):
        interfaces = Interface.objects.filter(device_ref=self)
        policy_in = PolicyIn.objects.get(policy_ref=self.policy_ref)
        env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        output = env.get_template("service_policy.j2")
        config_file = output.render(interfaces=interfaces, policy_in=policy_in)
        return config_file

    def no_service_policy(self):
        interfaces = Interface.objects.filter(device_ref=self)
        policy_in = PolicyIn.objects.get(policy_ref=self.policy_ref)
        env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        output = env.get_template("no_service_policy.j2")
        config_file = output.render(interfaces=interfaces, policy_in=policy_in)
        return config_file

    def deploy_policy(self, policy_id):
        police_in = PolicyIn.objects.get(policy_ref_id=policy_id)
        interfaces = Interface.objects.filter(device_ref=self, egress=True)
        interfaces2 = Interface.objects.filter(device_ref=self, wan=True)
        policies_out = []
        for interface in interfaces:
            policies_out.append(interface.policy_out_ref)
        for interface in interfaces2:
            policies_out.append(interface.policy_out_ref)
        env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        output = env.get_template("baseline.j2")
        config_file = output.render(policies=policies_out, device=self, police_in=police_in)
        connection = self.connect()
        print(connection)
        connection.load_merge_candidate(config=config_file)
        print(connection.compare_config())
        connection.commit_config()
        connection.close()
        # if self.wan() or self.ingress():
        #     config_file = police_in.add_applications
        #     connection.load_merge_candidate(config=config_file)
        #     connection.commit_config()
        #     config_policy = police_in.render_policy
        #     connection.load_merge_candidate(config=config_policy)
        #     connection.commit_config()
        # if self.egress():
        #     env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        #     output = env.get_template("all_policies.j2")
        #     config_file = output.render(policies=policies_out)
        #     connection.load_merge_candidate(config=config_file)
        #     connection.commit_config()
        # conf = self.service_policy()
        # connection.load_merge_candidate(config=conf)
        # connection.commit_config()
        # connection.close()

        return self.hostname + "this device Done"

    def remove_policy(self, policy_id):
        police_in = PolicyIn.objects.get(policy_ref_id=policy_id)
        interfaces = Interface.objects.filter(device_ref=self, egress=True)
        interfaces2 = Interface.objects.filter(device_ref=self, wan=True)
        policies_out = []
        for interface in interfaces:
            policies_out.append(interface.policy_out_ref)
        for interface in interfaces2:
            policies_out.append(interface.policy_out_ref)
        env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        output = env.get_template("no_baseline.j2")
        config_file = output.render(policies=policies_out, device=self, police_in=police_in)
        connection = self.connect()
        print(connection)
        connection.load_merge_candidate(config=config_file)
        print(connection.compare_config())
        connection.commit_config()
        connection.close()
        # police_in = PolicyIn.objects.get(policy_ref_id=policy_id)
        # policies_out = PolicyOut.objects.filter(policy_ref_id=policy_id)
        # connection = self.connect()
        # config_file = self.no_service_policy()
        # connection.load_merge_candidate(config=config_file)
        # connection.commit_config()
        # if self.wan() or self.ingress():
        #     config_policy = police_in.render_no_policy
        #     connection.load_merge_candidate(config=config_policy)
        #     connection.commit_config()
        #     config_file = police_in.remove_applications
        #     connection.load_merge_candidate(config=config_file)
        #     connection.commit_config()

        # if self.egress():
        #     env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
        #     output = env.get_template("remove_policies.j2")
        #     config_file = output.render(policies=policies_out)
        #     connection.load_merge_candidate(config=config_file)
        #     connection.commit_config()
        # connection.close()

        return self.hostname + "this device Done"


class Interface(models.Model):
    interface_name = models.CharField(max_length=255)
    ingress = models.BooleanField(default=False)
    device_ref = models.ForeignKey(Device, on_delete=models.CASCADE, null=True)
    egress = models.BooleanField(default=False)
    wan = models.BooleanField(default=False)

    policy_out_ref = models.ForeignKey(PolicyOut, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.interface_name

    def tuning_selection(self):
        classes = RegroupementClass.objects.filter(policy_out=self.policy_out_ref, group__priority__in=["4", "3"])
        e = 0
        queue = None
        for classe in classes:
            if classe.oppressed_tos is not None and classe.excessive_tos is not None:
                c = classe.oppressed_tos.c_ratio * int(classe.group.priority)
                if c > e:
                    e = c
                    queue = classe

        return queue

    def tuning(self):
        queue = self.tuning_selection()
        if queue is not None:
            queue.oppressed_tos.drop_min_old = queue.oppressed_tos.drop_min_new
            queue.oppressed_tos.drop_max_old = queue.oppressed_tos.drop_max_new
            min = int(queue.oppressed_tos.drop_min_new)
            print(min+1)
            minn=min+1
            queue.oppressed_tos.drop_min_new = str(minn)
            queue.oppressed_tos.drop_max_new = int(queue.oppressed_tos.drop_max_new)+1
            queue.oppressed_tos.save()
            print(queue.oppressed_tos.drop_min_new)
            print(queue.oppressed_tos.drop_max_new)
            # queue.oppressed_tos.save()
            # a = self.policy_out_ref
            #
            # TuningHistory.objects.create(tos=queue.oppressed_tos, policy_ref=a.policy_ref, timestamp=datetime.now())
            # # queue.oppressed_tos.drop_min = queue.excessive_tos.drop_min
            # # queue.oppressed_tos.drop_max = queue.excessive_tos.drop_max
            # # queue.excessive_tos.drop_min = min
            # # queue.excessive_tos.drop_max = max
            # a = self.policy_out_ref
            # env = Environment(loader=FileSystemLoader(str(MEDIA_ROOT[0]) + "/monitoring_conf/"))
            # named = env.get_template("tuning.j2")
            # config_file = named.render(a=a, queue=queue, oppressed_tos=queue.oppressed_tos,
            #                            excessive_tos=queue.excessive_tos)
            # return config_file
        else:
            print("noting to do ")


class TuningHistory(models.Model):
    tos = models.ForeignKey(Dscp, on_delete=models.CASCADE, null=True)
    policy_ref = models.ForeignKey(Policy, on_delete=models.CASCADE, null=True)
    timestamp = models.DateTimeField(null=False)

    @property
    def tos_interface(self):
        t = None
        interface = Interface.objects.get(policy_out_ref=self.tos.regroupement_class.policy_out)

        t = interface.interface_name
        return str(t)

    @property
    def dscp_value(self):
        return self.tos.dscp_value

    @property
    def drop_min_old(self):
        return self.tos.drop_min_old

    @property
    def drop_max_old(self):
        return self.tos.drop_max_old

    @property
    def drop_min_new(self):
        return self.tos.drop_min_new

    @property
    def drop_max_new(self):
        return self.tos.drop_max_new
