import hashlib
import mongoengine
from scapy.all import *
from scapy.layers.netflow import NetflowSession
from functools import partial
from .models import *
from ntplib import *
import requests


def calculate_time(sysUptime, collection_time, time):
    return (collection_time - (sysUptime / 1000)) + time / 1000


def dbcollect(phb_behavior: topology, pkt):
    sysUptime = pkt[NetflowHeaderV9].sysUptime
    collection_time = pkt[NetflowHeaderV9].unixSecs
    devices = phb_behavior.devices
    monitor = None
    for device in devices:
        if (device.management.management_address == pkt[IP].src):
            monitor = device
    flows = None
    try:
        flows = pkt[NetflowDataflowsetV9].records
        for record in flows:
            netflow_fields_ins = netflow_fields()
            netflow_fields_ins.counter_bytes = int.from_bytes(record.IN_BYTES, 'big')
            netflow_fields_ins.counter_pkts = int.from_bytes(record.IN_PKTS, 'big')
            netflow_fields_ins.first_switched = datetime.datetime.utcfromtimestamp(
                calculate_time(sysUptime, collection_time, record.FIRST_SWITCHED))
            netflow_fields_ins.last_switched = datetime.datetime.utcfromtimestamp(
                calculate_time(sysUptime, collection_time, record.LAST_SWITCHED))
            time = (record.LAST_SWITCHED - record.FIRST_SWITCHED) / 100
            if (time == 0):
                time = 0.0001
                netflow_fields_ins.bandwidth = int.from_bytes(record.IN_BYTES, 'big')  # bps
            else:

                netflow_fields_ins.bandwidth = int.from_bytes(record.IN_BYTES, 'big') * 8 / time  # bps
            input_interface = monitor.get_interface_by_index(int.from_bytes(record.INPUT_SNMP, 'big'))
            netflow_fields_ins.input_int = input_interface
            output_interface = monitor.get_interface_by_index(int.from_bytes(record.OUTPUT_SNMP, 'big'))
            netflow_fields_ins.output_int = output_interface
            netflow_fields_ins.collection_time = datetime.datetime.utcfromtimestamp(collection_time)
            print("-------------")
            print(record.IPV4_DST_ADDR)
            print(record.L4_DST_PORT)
            print("-------------")
            flow_input = "{}:{}->{}:{}|{}|{}|{}".format(str(record.IPV4_SRC_ADDR), str(record.L4_SRC_PORT),
                                                        str(record.IPV4_DST_ADDR), str(record.L4_SRC_PORT),
                                                        str(record.TOS),
                                                        str(int.from_bytes(record.APPLICATION_ID, 'big')),
                                                        str(record.PROTOCOL))
            flow_hash = hashlib.md5(flow_input.encode())

            src_device, dst_device = phb_behavior.get_ip_sla_devices(record)

            print(src_device.hostname, dst_device.hostname)

            flow_exist = None
            try:
                flow_exist = flow.objects(flow_id=flow_hash.hexdigest())[0]
            except:
                pass

            if (flow_exist == None):
                flow_ins = flow()
                flow_ins.flow_id = str(flow_hash.hexdigest())
                flow_ins.ipv4_src_addr = record.IPV4_SRC_ADDR
                flow_ins.ipv4_dst_addr = record.IPV4_DST_ADDR
                flow_ins.ipv4_protocol = record.PROTOCOL
                flow_ins.transport_src_port = record.L4_SRC_PORT
                flow_ins.transport_dst_port = record.L4_DST_PORT
                flow_ins.type_of_service = record.TOS
                flow_ins.application_ID = int.from_bytes(record.APPLICATION_ID, 'big')
                flow_ins.save()
                netflow_fields_ins.flow_ref = flow_ins
                netflow_fields_ins.device_ref = monitor
                netflow_fields_ins.save()
                if src_device != dst_device and record.TOS != 192 and record.TOS != 224:  # if someone ping the loopback or flow is for network control or internetwork control
                    print("I have passed")
                    similar_ip_sla = ip_sla.objects(sender_device_ref=src_device, responder_device_ref=dst_device,
                                                    type_of_service=record.TOS)  # verify if ip sla exists for this flow
                    if (len(similar_ip_sla) == 0):
                        if dst_device.is_responder == False:
                            dst_device.configure_ip_sla_responder()
                            dst_device.is_responder = True
                            dst_device.update(set__is_responder=True)
                        sla = ip_sla()
                        sla.sender_device_ref = src_device
                        sla.responder_device_ref = dst_device
                        sla.type_of_service = record.TOS
                        sla.save()
                        src_device.configure_ip_sla(sla.operation, dst_device.management.management_address, record.TOS)
                        flow_ins.ip_sla_ref = sla
                        flow_ins.update(set__ip_sla_ref=sla)
                    else:
                        flow_ins.ip_sla = similar_ip_sla[0]
                        flow_ins.update(set__ip_sla_ref=similar_ip_sla[0])
                        jitter, delay, pkt_loss = src_device.pull_ip_sla_stats(similar_ip_sla[0].operation)
                        sla_info_ins = ip_sla_info()
                        sla_info_ins.avg_jitter = jitter
                        sla_info_ins.avg_delay = delay
                        sla_info_ins.packet_loss = pkt_loss
                        sla_info_ins.timestamp = datetime.datetime.utcfromtimestamp(collection_time)
                        sla_info_ins.ip_sla_ref = similar_ip_sla[0]
                        sla_info_ins.save()

            else:
                netflow_fields_ins.device = monitor
                netflow_fields_ins.flow_ref = flow_exist[0]
                netflow_fields_ins.save()
                sla = ip_sla.objects(sender_device_ref=src_device, responder_device_ref=dst_device,
                                     type_of_service=flow_exist[0].type_of_service)
                jitter, delay, pkt_loss = src_device.pull_ip_sla_stats(sla[0].operation)
                sla_info = ip_sla_info()
                sla_info.avg_jitter = jitter
                sla_info.avg_delay = delay
                sla_info.packet_loss = pkt_loss
                sla_info.timestamp = datetime.datetime.utcfromtimestamp(sys_uptime)
                sla_info.ip_sla_ref = sla
                sla_info.save()
    except Exception as e:
        print(e)
        try:
            app_name = pkt[NetflowDataflowsetV9][NetflowOptionsRecordOptionV9].APPLICATION_NAME
            app_id = pkt[NetflowDataflowsetV9][NetflowOptionsRecordOptionV9].APPLICATION_ID
            app_ins = application(application_ID=int.from_bytes(app_id, "big"), application_NAME=app_name)
            app_ins.save()
        except Exception as e:
            pass


def Sniff_Netflow(phb_behavior):
    sniff(session=NetflowSession, filter="dst port 2055", prn=partial(dbcollect, phb_behavior))


def check_if_exists(cls, *args, **kwargs):
    try:
        ob = cls.objects.get(*args, **kwargs)
        return True
    except cls.DoesNotExist:
        return False


def add_device_api_call(topology_name, management_interface, management_address, username, password):
    json_data = {"management": {"management_interface": management_interface, "management_address": management_address,
                                "username": username, "password": password}, "topology_name": topology_name}
    print(topology_name, management_address, management_interface, username, password)
    api_url = "http://localhost:8000/api/v1/add-device"
    response = requests.post(url=api_url, json=json_data)
    print(response.status_code)
    # print(response.content)

    return response.content
