"""
This script parse XML files and fill database
with Person and PersonRole objects.

Person model contains data about all people which were
a membe of Congress at least one time.

PersonRole contains data about role of current congress members.
"""
from datetime import datetime
import logging, pprint

from parser.progress import Progress
from parser.processor import YamlProcessor, yaml_load
from parser.models import File
from person.models import Person, PersonRole, Gender, RoleType, SenatorClass

from settings import CURRENT_CONGRESS, CONGRESS_LEGISLATORS_PATH

log = logging.getLogger('parser.person_parser')

class PersonProcessor(YamlProcessor):
    """
    Person model contains data about all people which were
    a member of Congress at least one time.
    """

    REQUIRED_ATTRIBUTES = ['id_govtrack', 'name_first', 'name_last']
    ATTRIBUTES = [
        'id_govtrack', 'name_first', 'name_last',
        'name_middle', 'name_suffix', 'name_nickname',
        'id_bioguide', 'id_votesmart', 'id_opensecrets', 'id_cspan',
        'social_youtube', 'social_twitter',
        'bio_birthday', 'bio_gender',
    ]
    GENDER_MAPPING = {'M': Gender.male, 'F': Gender.female}
    FIELD_MAPPING = {
        'id_govtrack': 'id',
        'id_bioguide': 'bioguideid',
        'id_votesmart': 'pvsid',
        'id_opensecrets': 'osid',
        'id_cspan': 'cspanid',
        'social_youtube': 'youtubeid',
        'social_twitter': 'twitterid',
        'name_first': 'firstname',
        'name_last': 'lastname',
        'bio_birthday': 'birthday',
        'bio_gender': 'gender',
        'name_middle': 'middlename',
        'name_suffix': 'namemod',
        'name_nickname': 'nickname',
    }

    def bio_gender_handler(self, value):
        return self.GENDER_MAPPING[value]

    def bio_birthday_handler(self, value):
        return datetime.strptime(value, '%Y-%m-%d')

    def id_handler(self, value):
        return int(value)
    def cspanid_handler(self, value):
        return int(value)


class PersonRoleProcessor(YamlProcessor):
    """
    PersonRole contains data about role of current congress members.
    """

    REQUIRED_ATTRIBUTES = ['type', 'start', 'end']
    ATTRIBUTES = [
        'type', 'start', 'end', 'class',
        'district', 'state', 'party', 'url'
    ]
    FIELD_MAPPING = {
        'type': 'role_type',
        'start': 'startdate',
        'end': 'enddate',
        'class': 'senator_class',
        'url': 'website'
    }
    ROLE_TYPE_MAPPING = {
        'rep': RoleType.representative,
        'sen': RoleType.senator,
        'prez': RoleType.president,
        'viceprez': RoleType.vicepresident}
    SENATOR_CLASS_MAPPING = {1: SenatorClass.class1, 2: SenatorClass.class2,
                             3: SenatorClass.class3}

    def type_handler(self, value):
        return self.ROLE_TYPE_MAPPING[value]

    def start_handler(self, value):
        return datetime.strptime(value, '%Y-%m-%d').date()

    def end_handler(self, value):
        return datetime.strptime(value, '%Y-%m-%d').date()

    def class_handler(self, value):
        return self.SENATOR_CLASS_MAPPING[value]


def main(options):
    """
    Update Person and PersonRole models.
    
    Do safe update: touch only those records
    which have been changed.
    """

    BASE_PATH = CONGRESS_LEGISLATORS_PATH
    SRC_FILES = ['legislators-current', 'legislators-historical', 'legislators-social-media', 'executive'] # order matters

    for p in SRC_FILES:
        f = BASE_PATH + p + ".yaml"
        if not File.objects.is_changed(f) and not options.force:
            log.info('File %s was not changed' % f)
        else:
            # file modified...
            break
    else:
        # no 'break' ==> no files modified
        return

    # Start parsing.
    
    had_error = False

    # Get combined data.
    legislator_data = { }
    leg_id_map = { }
    for p in SRC_FILES:
        log.info('Opening %s...' % p)
        f = BASE_PATH + p + ".yaml"
        y = yaml_load(f)
        for m in y:
            if p != 'legislators-social-media':
                govtrack_id = m["id"].get("govtrack")
                
                # For the benefit of the social media file, make a mapping of IDs.
                for k, v in m["id"].items():
                    if type(v) != list:
                        leg_id_map[(k,v)] = govtrack_id
            else:
                # GovTrack IDs are not always listed in this file.
                for k, v in m["id"].items():
                    if type(v) != list and (k, v) in leg_id_map:
                        govtrack_id = leg_id_map[(k,v)]
                        break
            
            if not govtrack_id:
                print "No GovTrack ID:"
                pprint.pprint(m)
                had_error = True
                continue
                
            if govtrack_id not in legislator_data:
                legislator_data[govtrack_id] = m
            elif p == "legislators-social-media":
                legislator_data[govtrack_id]["social"] = m["social"]
            elif p == "executive":
                legislator_data[govtrack_id]["terms"].extend( m["terms"] )
            else:
                raise ValueError("Duplication in an unexpected way.")
    
    person_processor = PersonProcessor()
    role_processor = PersonRoleProcessor()

    existing_persons = set(Person.objects.values_list('pk', flat=True))
    processed_persons = set()
    created_persons = set()

    progress = Progress(total=len(legislator_data))
    log.info('Processing persons')

    for node in legislator_data.values():
        # Wrap each iteration in try/except
        # so that if some node breaks the parsing process
        # then other nodes could be parsed
        try:
            person = person_processor.process(Person(), node)
            
            # Create cached name strings. This is done again later
            # after the roles are updated.
            person.set_names()

            # Now try to load the person with such ID from
            # database. If found it then just update it
            # else create new Person object
            try:
                ex_person = Person.objects.get(pk=person.pk)
                if person_processor.changed(ex_person, person) or options.force:
                    # If the person has PK of existing record,
                    # coming in via the YAML-specified GovTrack ID,
                    # then Django ORM will update existing record
                    if not options.force:
                        log.warn("Updated %s" % person)
                    person.save()
                    
            except Person.DoesNotExist:
                created_persons.add(person.pk)
                person.save()
                log.warn("Created %s" % person)

            processed_persons.add(person.pk)

            # Process roles of the person
            roles = list(PersonRole.objects.filter(person=person))
            existing_roles = set(PersonRole.objects.filter(person=person).values_list('pk', flat=True))
            processed_roles = set()
            role_list = []
            for role in node['terms']:
                role = role_processor.process(PersonRole(), role)
                role.person = person
                
                role.current = role.startdate <= datetime.now().date() and role.enddate >= datetime.now().date() # \
                        #and CURRENT_CONGRESS in role.congress_numbers()
                
                # Try to match this role with one already in the database.
                # First search for an exact match on type/start/end.
                ex_role = None
                for r in roles:
                    if role.role_type == r.role_type and r.startdate == role.startdate and r.enddate == role.enddate:
                        ex_role = r
                        break
                        
                # Otherwise match on type/start only.
                if not ex_role:
                    for r in roles:
                        if role.role_type == r.role_type and r.startdate == role.startdate:
                            ex_role = r
                            break
                        
                if ex_role:    
                    # These roles correspond.
                    processed_roles.add(ex_role.id)
                    role.id = ex_role.id
                    if role_processor.changed(ex_role, role) or options.force:
                        role.save()
                        role_list.append(role)
                        if not options.force:
                            log.warn("Updated %s" % role)
                    roles.remove(ex_role) # don't need to try matching this to any other node
                else:
                    # Didn't find a matching role.
                    if len([r for r in roles if r.role_type == role.role_type]) > 0:
                        print role, "is one of these?"
                        for ex_role in roles:
                            print "\t", ex_role
                        raise Exception("There is an unmatched role.")
                    log.warn("Created %s" % role)
                    role.save()
                    role_list.append(role)
                        
            # create the events for the roles after all have been loaded
            # because we don't create events for ends of terms and
            # starts of terms that are adjacent.
            if not options.disable_events:
                for i in xrange(len(role_list)):
                    role_list[i].create_events(
                        role_list[i-1] if i > 0 else None,
                        role_list[i+1] if i < len(role_list)-1 else None
                        )
            
            removed_roles = existing_roles - processed_roles
            for pk in removed_roles:
                pr = PersonRole.objects.get(pk=pk)
                print pr.person.id, pr
                raise ValueError("Deleted role??")
                log.warn("Deleted %s" % pr)
                pr.delete()
            
            # The name can't be determined until all of the roles are set. If
            # it changes, re-save. Unfortunately roles are cached so this actually
            # doesn't work yet. Re-run the parser to fix names.
            nn = (person.name, person.sortname)
            if hasattr(person, "role"): delattr(person, "role") # clear the cached info
            person.set_names()
            if nn != (person.name, person.sortname):
                log.warn("%s is now %s." % (nn[0], person.name))
                person.save()
            
        except Exception, ex:
            # Catch unexpected exceptions and log them
            pprint.pprint(node)
            log.error('', exc_info=ex)
            had_error = True

        progress.tick()

    log.info('Processed persons: %d' % len(processed_persons))
    log.info('Created persons: %d' % len(created_persons))
    
    if not had_error:
        # Remove person which were not found in XML file
        removed_persons = existing_persons - processed_persons
        for pk in removed_persons:
            p = Person.objects.get(pk=pk)
            if p.roles.all().count() > 0:
                log.warn("Missing? Deleted? %d: %s" % (p.id, p))
            else:
                log.warn("Deleting... %d: %s (remember to prune_index!)" % (p.id, p))
                raise Exception("Won't delete!")
                p.delete()
        log.info('Missing/deleted persons: %d' % len(removed_persons))
    
        # Mark the files as processed.
        for p in SRC_FILES:
            f = BASE_PATH + p + ".yaml"
            File.objects.save_file(f)


if __name__ == '__main__':
    main()
