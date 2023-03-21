# ngsweb

Test webapplicatie voor toegang tot irods en het lsf rekencluster

Maakt gebruik van
* flask [http://flask.pocoo.org/](http://flask.pocoo.org/)
* python-irodsclient [https://github.com/irods/python-irodsclient](https://github.com/irods/python-irodsclient)
* bootstrap library [https://getbootstrap.com/](https://getbootstrap.com/)
* conda

Start de applicatie met behulp van het script start.sh

## Docker
### Docker-compose build
To build the docker image, use a server that has docker installed (e.g., `rivm-bioir-l02t`).
Clone the repository to this server and run the following command to build the image:
```
sudo docker-compose build
```

### Docker-compose run
To run the image, use the following command:
```
sudo docker-compose up
```

to enter the container:
```
sudo docker-compose exec ngsweb bin/bash
```

#### Development configuration
By default, this uses the `docker-compose.yml` file for the configuration.
If a `docker-compose.override.yml` is present, it uses this file to override/extend the settings of the `docker-compose.yml` file.

For development, we have a standard setting override in `docker-compose.development.yml`. To use this, do the following before running:
```
ln -s docker-compose.development.yml docker-compose.override.yml
```
this creates a symlink called `docker-compose.override.yml` which links to `docker-compose.development.yml`.
Unlinking is done with `unlink docker-compose.override.yml`.

### clean images
Docker images and containers take up quite a bit of space, so you should clean up regularly. Prune the unused images with:
```
docker images prune
```
and clean up the containers with:
```
docker rm $(docker ps -aq)
```

### open ports
To view the ngsweb app in the browser, you will need to use an open port to runs on.
On rivm-biofl-l01t, the ports 2048-2148 are open for testing.

If you need to turn off the firewall, you can disable puppet temporarily by setting
`noop = true` in `/etc/puppetlabs/puppet/puppet.conf`.

Perhaps you also need to disable puppet with:
```
sudo systemctl stop puppet
```
and disable the firewall fully with:
```
sudo iptables -F
```


