from itertools import groupby

from background_task import background

from QoSmanager.models import *
from .utils import *
from .models import *
from datetime import datetime
import time
import paho.mqtt.client as mqtt

server = "postman.cloudmqtt.com"
port = 11494
username = "qvjbfmpb"
password = "x6lBEK-EESRM"
my_client = mqtt.Client()


def connect():
    my_client.username_pw_set(username=username, password=password)
    my_client.connect(host=server, port=port)


def on_connect(client, userdata, flags, rc):
    print("Connected with result code " + str(rc))
    # subscription in on_connect means that the subscription will be renewed
    # if we re-connect in case of loosing the connection
    # client.subscribe("$SYS/#")


def publish(topic, payload, qos, retain):
    return my_client.publish(topic=topic, payload=payload, qos=qos, retain=retain)


def on_publish(client, userdata, mid):
    print("mid: " + str(mid))


@background(queue='q1')
def sniff_back(phb_behavior):
    topo = topology.objects(topology_name=phb_behavior)[0]
    print("Strting ... ")
    Sniff_Netflow(topo)
    return None


@background(queue='q2')
def Initialize_mqtt_client():
    my_client.on_connect = on_connect
    my_client.on_publish = on_publish
    connect()
    time.sleep(5)
    publish(topic="LimitBreach/J", payload="Jitter Limit breach", qos=1, retain=False)

    slainfo = ip_sla_info.objects(avg_jitter__lte=5)

    for sla in slainfo:
        publish(topic="LimitBreach/J", payload="Jitter Limit breach", qos=1, retain=False)

    notification_ins = notification(message="Jitter Breach", timestampt=str(datetime.now()))

    my_client.loop_forever()
    return None


@background(queue='q1')
def add_device_api_call1(topology_name, management_interface, management_address, username, password):
    json_data = {"management": {"management_interface": management_interface, "management_address": management_address,
                                "username": username, "password": password}, "topology_name": topology_name}
    print(topology_name, management_address, management_interface, username, password)
    api_url = "http://localhost:8000/api/v1/add-device"
    response = requests.post(url=api_url, json=json_data)
    print(response.status_code)
    print(response.content)

    return response.content


def prepare_env_api_call(topology_name):
    json_data = {"topology": topology_name}
    print(topology_name)

    api_url = "http://localhost:8000/api/v1/preapare-env"
    response = requests.post(url=api_url, json=json_data)
    print(response.status_code)
    print(response.content)

    return response.content


def discover_network_api_call(topology_name):
    json_data = {"topology": topology_name}

    api_url = "http://localhost:8000/api/v1/discover-network"
    response = requests.post(url=api_url, json=json_data)
    print(response.status_code)
    print(response.content)

    return response.content


def configure_monitoring_api_call(topology_name, destination):
    json_data = {"topology": topology_name, "destination": destination}

    api_url = "http://localhost:8000/api/v1/configure-monitoring"
    response = requests.post(url=api_url, json=json_data)
    print(response.status_code)
    print(response.content)

    return response.content


def start_monitoring_api_call(topology_name):
    json_data = {"topology": topology_name}

    api_url = "http://localhost:8000/api/v1/start-monitoring"
    response = requests.post(url=api_url, json=json_data)
    print(response.status_code)
    print(response.content)

    return response.content


@background(schedule=60)
def nbar_discovery_task(end_time, policy_id):
    dvcs = Device.objects.filter(policy_ref_id=policy_id)
    threads = []
    print("enabling nbar in devices")
    for dvcs in dvcs:
        threads.append(Thread(target=dvcs.enable_nbar))
    for th in threads:
        print("nbar thread")
        th.start()
    for th in threads:
        th.join()

    while datetime.now() < datetime.strptime(end_time, '%Y/%m/%d %H:%M'):
        devices = Device.objects.filter(policy_ref_id=policy_id)
        application = []
        print("discovering start now ")
        for device in devices:
            application.extend(device.discovery_application())
        print("application:")
        print(set(application))
        for app in set(application):
            c = False
            b = BusinessApp.objects.filter(name=app)
            print(len(b))
            for a in b:
                b_id = a.id
                print("name:", a.name)
                if len(Application.objects.filter(business_app=a,
                                                  policy_in=PolicyIn.objects.get(policy_ref=policy_id))) != 0:
                    c = True
            if len(b) != 0 and not c:
                print("save the application")
                ap = Application.objects.create(business_app=BusinessApp.objects.get(id=b_id),
                                                source="any", destination="any", begin_time="00:00",
                                                end_time="23:59",
                                                business_type=BusinessApp.objects.get(id=b_id).business_type,
                                                policy_in=PolicyIn.objects.get(policy_ref_id=policy_id),
                                                mark=BusinessApp.objects.get(id=b_id).recommended_dscp)
                if ap.mark.startswith("A"):
                    ap.group = Group.objects.get(priority=ap.app_priority, policy_id=policy_id)
                    ap.save()
                if ap.mark == "EF":
                    ap.group = Group.objects.get(priority="EF", policy_id=policy_id)
                    ap.save()
                elif ap.mark == "DEFAULT":
                    ap.group = Group.objects.get(priority="DEFAULT", policy_id=policy_id)
                    ap.save()
                elif ap.mark == "CS6":
                    ap.group = Group.objects.get(priority="CS6", policy_id=policy_id)
                    ap.save()
                elif ap.mark == "CS5":
                    ap.group = Group.objects.get(priority="CS5", policy_id=policy_id)
                    ap.save()
                elif ap.mark == "CS4":
                    ap.group = Group.objects.get(priority="CS4", policy_id=policy_id)
                    ap.save()
                elif ap.mark == "CS3":
                    ap.group = Group.objects.get(priority="CS3", policy_id=policy_id)
                    ap.save()
                elif ap.mark == "CS2":
                    ap.group = Group.objects.get(priority="CS2", policy_id=policy_id)
                    ap.save()
                elif ap.mark == "CS1":
                    ap.group = Group.objects.get(priority="CS1", policy_id=policy_id)
                    ap.save()
                else:
                    ap.save()
        print("slepp ")
        time.sleep(60)


@background(queue='q5')
def all_in_task(topology_id, policy_id, start_time):
    topo = Topology.objects.get(id=topology_id)
    a = Policy.objects.get(id=policy_id)
    devices = Device.objects.filter(topology_ref_id=topo)
    for device in devices:
        print("set the policy ref in device: " + device.hostname)
        device.policy_ref = a
        device.save()
    print("policy In creation")
    PolicyIn.objects.create(policy_ref=a, id=a.id)
    interfaces = Interface.objects.filter(ingress=False)
    Group.objects.create(name="VOIP", priority="EF", policy=a)
    Group.objects.create(name="business", priority="4", policy=a)
    Group.objects.create(name="critical", priority="3", policy=a)
    Group.objects.create(name="non-business", priority="2", policy=a)
    Group.objects.create(name="non-business2", priority="1", policy=a)
    Group.objects.create(name="Control", priority="CS6", policy=a)
    Group.objects.create(name="BRODCAST-VEDIO", priority="CS5", policy=a)
    Group.objects.create(name="Real-time", priority="CS4", policy=a)
    Group.objects.create(name="Call-Segnialing", priority="CS3", policy=a)
    Group.objects.create(name="OAM", priority="CS2", policy=a)
    Group.objects.create(name="Best-Effort", priority="DEFAULT", policy=a)
    Group.objects.create(name="Scavengers", priority="CS1", policy=a)

    for interface in interfaces:
        po = PolicyOut.objects.create(policy_ref=a)
        interface.policy_out_ref = po
        interface.save()
        # print(interface)

        realtime = RegroupementClass.objects.create(priority="100",
                                                    group=Group.objects.get(priority="EF", policy=a),
                                                    policy_out=po)
        Dscp.objects.create(dscp_value="EF", regroupement_class=realtime)
        policing = Policing.objects.create(cir="35", pir="40", dscp_transmit="AF21")
        shaping = Shaping.objects.create(peak="10", average="10")
        high = RegroupementClass.objects.create(shaping=shaping, policing=policing, bandwidth="35",
                                                group=Group.objects.get(priority="4", policy=a),
                                                policy_out=po)
        af43 = Dscp.objects.create(dscp_value="AF43", regroupement_class=high, drop_max="85", drop_min="70",
                                   denominator="20")
        af43.drop_max_old = af43.drop_max
        af43.drop_max_new = af43.drop_max
        af43.drop_min_old = af43.drop_min
        af43.drop_min_new = af43.drop_min
        af43.save()
        TuningHistory.objects.create(tos=af43, policy_ref=a, timestamp=datetime.now())
        af42 = Dscp.objects.create(dscp_value="AF42", regroupement_class=high, drop_max="95", drop_min="80",
                                   denominator="15")
        af42.drop_max_old = af42.drop_max
        af42.drop_max_new = af42.drop_max
        af42.drop_min_old = af42.drop_min
        af42.drop_min_new = af42.drop_min
        af42.save()
        TuningHistory.objects.create(tos=af42, policy_ref=a, timestamp=datetime.now())
        af41 = Dscp.objects.create(dscp_value="AF41", regroupement_class=high, drop_max="100", drop_min="90",
                                   denominator="10")
        af41.drop_max_old = af41.drop_max
        af41.drop_max_new = af41.drop_max
        af41.drop_min_old = af41.drop_min
        af41.drop_min_new = af41.drop_min
        af41.save()
        TuningHistory.objects.create(tos=af41, policy_ref=a, timestamp=datetime.now())
        policing = Policing.objects.create(cir="25", pir="30", dscp_transmit="AF11")
        shaping = Shaping.objects.create(peak="10", average="10")
        priority = RegroupementClass.objects.create(shaping=shaping, policing=policing, bandwidth="25",
                                                    group=Group.objects.get(priority="3", policy=a),
                                                    policy_out=po)
        af33 = Dscp.objects.create(dscp_value="AF33", regroupement_class=priority, drop_max="45", drop_min="35",
                                   denominator="45")
        af33.drop_max_old = af33.drop_max
        af33.drop_max_new = af33.drop_max
        af33.drop_min_old = af33.drop_min
        af33.drop_min_new = af33.drop_min
        af33.save()
        TuningHistory.objects.create(tos=af33, policy_ref=a, timestamp=datetime.now())
        af32 = Dscp.objects.create(dscp_value="AF32", regroupement_class=priority, drop_max="50", drop_min="40",
                                   denominator="40")
        af32.drop_max_old = af32.drop_max
        af32.drop_max_new = af32.drop_max
        af32.drop_min_old = af32.drop_min
        af32.drop_min_new = af32.drop_min
        af32.save()
        TuningHistory.objects.create(tos=af32, policy_ref=a, timestamp=datetime.now())
        af31 = Dscp.objects.create(dscp_value="AF31", regroupement_class=priority, drop_max="65", drop_min="55",
                                   denominator="35")
        af31.drop_max_old = af31.drop_max
        af31.drop_max_new = af31.drop_max
        af31.drop_min_old = af31.drop_min
        af31.drop_min_new = af31.drop_min
        af31.save()
        TuningHistory.objects.create(tos=af31, policy_ref=a, timestamp=datetime.now())
        policing = Policing.objects.create(cir="10", pir="10", dscp_transmit="AF31")
        shaping = Shaping.objects.create(peak="10", average="15")
        med = RegroupementClass.objects.create(shaping=shaping, policing=policing, bandwidth="10",
                                               group=Group.objects.get(priority="2", policy=a),
                                               policy_out=po)
        af23 = Dscp.objects.create(dscp_value="AF23", regroupement_class=med, drop_max="30", drop_min="23",
                                   denominator="60")
        af23.drop_max_old = af23.drop_max
        af23.drop_max_new = af23.drop_max
        af23.drop_min_old = af23.drop_min
        af23.drop_min_new = af23.drop_min
        af23.save()
        TuningHistory.objects.create(tos=af23, policy_ref=a, timestamp=datetime.now())
        af22 = Dscp.objects.create(dscp_value="AF22", regroupement_class=med, drop_max="35", drop_min="27",
                                   denominator="55")
        af22.drop_max_old = af22.drop_max
        af22.drop_max_new = af22.drop_max
        af22.drop_min_old = af22.drop_min
        af22.drop_min_new = af22.drop_min
        af22.save()
        TuningHistory.objects.create(tos=af22, policy_ref=a, timestamp=datetime.now())
        af21 = Dscp.objects.create(dscp_value="AF21", regroupement_class=med, drop_max="40", drop_min="33",
                                   denominator="50")
        af21.drop_max_old = af21.drop_max
        af21.drop_max_new = af21.drop_max
        af21.drop_min_old = af21.drop_min
        af21.drop_min_new = af21.drop_min
        af21.save()
        TuningHistory.objects.create(tos=af21, policy_ref=a, timestamp=datetime.now())
        policing = Policing.objects.create(cir="10", pir="10", dscp_transmit="AF31")
        shaping = Shaping.objects.create(peak="5", average="10")
        low = RegroupementClass.objects.create(shaping=shaping, policing=policing, bandwidth="5",
                                               group=Group.objects.get(priority="1", policy=a),
                                               policy_out=po)
        af13 = Dscp.objects.create(dscp_value="AF13", regroupement_class=low, drop_max="15", drop_min="10",
                                   denominator="80")
        af13.drop_max_old = af13.drop_max
        af13.drop_max_new = af13.drop_max
        af13.drop_min_old = af13.drop_min
        af13.drop_min_new = af13.drop_min
        af13.save()
        TuningHistory.objects.create(tos=af13, policy_ref=a, timestamp=datetime.now())
        af12 = Dscp.objects.create(dscp_value="AF12", regroupement_class=low, drop_max="20", drop_min="13",
                                   denominator="70")
        af12.drop_max_old = af12.drop_max
        af12.drop_max_new = af12.drop_max
        af12.drop_min_old = af12.drop_min
        af12.drop_min_new = af12.drop_min
        af12.save()
        TuningHistory.objects.create(tos=af12, policy_ref=a, timestamp=datetime.now())
        af11 = Dscp.objects.create(dscp_value="AF11", regroupement_class=low, drop_max="25", drop_min="17",
                                   denominator="65")
        af11.drop_max_old = af11.drop_max
        af11.drop_max_new = af11.drop_max
        af11.drop_min_old = af11.drop_min
        af11.drop_min_new = af11.drop_min
        af11.save()
        TuningHistory.objects.create(tos=af11, policy_ref=a, timestamp=datetime.now())
    dvcs = Device.objects.filter(policy_ref_id=policy_id)
    threads = []
    print("enabling nbar")
    for dvcs in dvcs:
        threads.append(Thread(target=dvcs.enable_nbar))
    for th in threads:
        print("start thread")
        th.start()
    for th in threads:
        th.join()
    while datetime.now() < datetime.strptime(start_time, '%Y/%m/%d %H:%M'):
        devices = Device.objects.filter(policy_ref_id=policy_id)
        application = []
        for device in devices:
            application.extend(device.discovery_application())
        print("application:...")
        print("saha:...")
        print(set(application))
        for app in set(application):
            print(app)
            c = False
            b = BusinessApp.objects.filter(name=app)
            # print(len(b))
            for a in b:
                b_id = a.id
                # print("name:", a.name)
                if len(Application.objects.filter(business_app=a,
                                                  policy_in=PolicyIn.objects.get(policy_ref=policy_id))) != 0:
                    c = True
                    print("hada howa propblem")
            if len(b) != 0 and not c:
                print("save the application")
                ap = Application.objects.create(business_app=BusinessApp.objects.get(id=b_id),
                                                source="any", destination="any", begin_time="00:00",
                                                end_time="23:59",
                                                business_type=BusinessApp.objects.get(id=b_id).business_type,
                                                policy_in=PolicyIn.objects.get(policy_ref_id=policy_id),
                                                mark=BusinessApp.objects.get(id=b_id).recommended_dscp)
                if ap.mark.startswith("A"):
                    ap.group = Group.objects.get(priority=ap.app_priority, policy_id=policy_id)
                    ap.save()
                if ap.mark == "EF":
                    ap.group = Group.objects.get(priority="EF", policy_id=policy_id)
                    ap.save()
                elif ap.mark == "DEFAULT":
                    ap.group = Group.objects.get(priority="DEFAULT", policy_id=policy_id)
                    ap.save()
                elif ap.mark == "CS6":
                    ap.group = Group.objects.get(priority="CS6", policy_id=policy_id)
                    ap.save()
                elif ap.mark == "CS5":
                    ap.group = Group.objects.get(priority="CS5", policy_id=policy_id)
                    ap.save()
                elif ap.mark == "CS4":
                    ap.group = Group.objects.get(priority="CS4", policy_id=policy_id)
                    ap.save()
                elif ap.mark == "CS3":
                    ap.group = Group.objects.get(priority="CS3", policy_id=policy_id)
                    ap.save()
                elif ap.mark == "CS2":
                    ap.group = Group.objects.get(priority="CS2", policy_id=policy_id)
                    ap.save()
                elif ap.mark == "CS1":
                    ap.group = Group.objects.get(priority="CS1", policy_id=policy_id)
                    ap.save()
                else:
                    ap.save()
        print("slepp ")
        time.sleep(60)
    devices = Device.objects.filter(policy_ref_id=policy_id)
    threads = []
    for device in devices:
        threads.append(Thread(target=device.deploy_policy, args=[policy_id]))
    for th in threads:
        print("start thread")
        th.start()
    for th in threads:
        th.join()
    policy = Policy.objects.get(id=policy_id)
    policy.deploy = True
    policy.save()


def retrieve_monitoring():
    url = "http://127.0.0.1:8000/api/v1/flowtabletworates?topology=test&time_start=2019-09-10%2014:41:00&time_end=2019-09-14%2014:41:00"
    r = requests.get(url)
    # print(r.json())
    data = r.json()
    dict = {}

    for elem in data['data']:
        if elem[1] not in dict:
            dict[elem[1]] = []
        dict[elem[1]].append(elem[2:])

    # for k in dict:
    #     if dict[k][0] not in dict2:
    #         dict2[dict[k][0]] = []
    #     dict2[dict[k][0]].append(dict[k][0:])
    for k in dict:
        dict2 = {}
        for elem in dict[k]:
            if elem[0] not in dict2:
                dict2[elem[0]] = []
            dict2[elem[0]].append(elem[7:])
        dict[k] = dict2
    for k in dict:
        for e in dict[k]:
            dict2 = {}
            for elem in dict[k][e]:
                if elem[0] not in dict2:
                    dict2[elem[0]] = []
                dict2[elem[0]].append(elem[0:])
            dict[k][e] = dict2

    class_4 = ['152', '144', '136']
    class_3 = ['120', '112', '104']

    for device in dict:
        dev = Device.objects.get(topology_ref_id=1, hostname=device)
        print(dev)
        for interface in dict[device]:
            port = Interface.objects.filter(egress=True, device_ref=dev, interface_name=interface) | \
                   Interface.objects.filter(wan=True, device_ref=dev, interface_name=interface)
            sum_4 = 0
            sum_3 = 0
            print("-----------------------------")
            if len(port) != 0:
                print(port[0])
                for tos in dict[device][interface]:
                    if str(tos) in class_4 or class_3:
                        policy = port[0].policy_out_ref
                        print("the policy", policy)
                        regs = RegroupementClass.objects.filter(policy_out=policy, group__priority__in=["4", "3"])
                        classe = []
                        for reg in regs:
                            if tos == 152:
                                classe = Dscp.objects.filter(regroupement_class=reg, dscp_value="AF43")
                            elif tos == 144:
                                classe = Dscp.objects.filter(regroupement_class=reg, dscp_value="AF43")
                            elif tos == 136:
                                classe = Dscp.objects.filter(regroupement_class=reg, dscp_value="AF42")

                            elif tos == 120:
                                classe = Dscp.objects.filter(regroupement_class=reg, dscp_value="AF33")
                            elif tos == 112:
                                classe = Dscp.objects.filter(regroupement_class=reg, dscp_value="AF32")
                            elif tos == 104:
                                classe = Dscp.objects.filter(regroupement_class=reg, dscp_value="AF31")
                            if len(classe) != 0:

                                print("-----------------------------")
                                print(tos)

                                sum = 0
                                loss_incr = 0
                                delay_incr = 0
                                jitter_incr = 0
                                sum_delay = 0
                                sum_jitter = 0
                                sum_loss = 0
                                for i in dict[device][interface][tos]:
                                    print("the packet loss  is :", i[7])
                                    print("the jitter  is :", i[6])
                                    print("the delay  is :", i[5])
                                    sum += int(i[2])
                                    if str(i[5]).isdigit():
                                        delay_incr += 1
                                        sum_delay += int(i[5])
                                    if str(i[6]).isdigit():
                                        jitter_incr += 1
                                        sum_jitter += int(i[6])
                                    if str(i[7]).isdigit():
                                        loss_incr += 1
                                        sum_loss += int(i[7])
                                    if str(tos) in class_4:
                                        print("class 4")
                                        sum_4 += sum
                                    elif str(tos) in class_3:
                                        print("class 3")
                                        sum_3 += sum
                                    else:
                                        print(tos)

                                print("the sum for this tos ", tos)
                                print(sum)
                                print("the delay average")
                                if delay_incr != 0:
                                    print(sum_delay / delay_incr)
                                    classe[0].delay = round(sum_delay / delay_incr)
                                    classe[0].save()
                                else:
                                    print("devision par 0")
                                print("the loss average")
                                if loss_incr != 0:
                                    print(sum_loss / loss_incr)
                                    classe[0].loss = round(sum_loss / loss_incr)
                                    classe[0].save()
                                else:
                                    print("devision par 0")

                            if reg.group.priority == "4":
                                reg.bits = round(sum_4)
                                reg.save()
                            if reg.group.priority == "3":
                                reg.bits = round(sum_3)
                                reg.save()


@background(queue='q9')
def tuning_task():
    print('start')
    c = 0
    while c <= 15:
        c += 1
        interfaces = Interface.objects.filter(wan=True)
        print(len(interfaces))
        policyout = interfaces[0].policy_out_ref
        policy = policyout.policy_ref
        a = 72
        regs = RegroupementClass.objects.filter(policy_out=policyout, group__priority__in=["4", "3"])
        for reg in regs:
            classes = Dscp.objects.filter(regroupement_class=reg)
            for classe in classes:

                if classe.dscp_value == "AF43":
                    print(classe.drop_min_new)
                    classe.drop_min_old = classe.drop_min_new
                    classe.drop_max_old = classe.drop_max_new
                    classe.drop_min_new = str(int(classe.drop_min_new) + 1)
                    classe.drop_max_new = str(int(classe.drop_max_new) + 1)

                    TuningHistory.objects.create(tos=classe, policy_ref=policy, timestamp=datetime.now())
                    classe.save()
                elif classe.dscp_value == "AF33":
                    print(classe.drop_min_new)
                    classe.drop_min_old = classe.drop_min_new
                    classe.drop_max_old = classe.drop_max_new
                    classe.drop_min_new = str(int(classe.drop_min_new) + 1)
                    classe.drop_max_new = str(int(classe.drop_max_new) + 1)

                    TuningHistory.objects.create(tos=classe, policy_ref=policy, timestamp=datetime.now())
                    classe.save()


    # regs = RegroupementClass.objects.filter(group__priority__in=["4", "3"])
    # for reg in regs:
    #     print(reg.group.priority)
    #     print(reg.oppressed_tos.dscp_value)
