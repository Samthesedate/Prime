import hashlib
import json
from datetime import datetime
from time import time
from urllib.parse import urlparse
from uuid import uuid4

import pandas as pd
import requests
from flask import Flask, jsonify, render_template, request


class Blockchain:
    def __init__(self):
        self.current_transactions = []
        self.chain = []
        self.nodes = set()

        # Create the genesis block
        self.new_block(previous_hash='1', proof=100)

    def register_node(self, address):
        """
        Add a new node to the list of nodes

        :param address: Address of node. Eg. 'http://192.168.0.5:5000'
        """

        parsed_url = urlparse(address)
        if parsed_url.netloc:
            self.nodes.add(parsed_url.netloc)
        elif parsed_url.path:
            # Accepts an URL without scheme like '192.168.0.5:5000'.
            self.nodes.add(parsed_url.path)
        else:
            raise ValueError('Invalid URL')

    def valid_chain(self, chain):
        """
        Determine if a given blockchain is valid

        :param chain: A blockchain
        :return: True if valid, False if not
        """

        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print("\n-----------\n")
            # Check that the hash of the block is correct
            last_block_hash = self.hash(last_block)
            if block['previous_hash'] != last_block_hash:
                return False

            # Check that the Proof of Work is correct
            if not self.valid_proof(
                    last_block['proof'], block['proof'], last_block_hash):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self):
        """
        This is our consensus algorithm, it resolves conflicts
        by replacing our chain with the longest one in the network.

        :return: True if our chain was replaced, False if not
        """

        neighbours = self.nodes
        new_chain = None

        # We're only looking for chains longer than ours
        max_length = len(self.chain)

        # Grab and verify the chains from all the nodes in our network
        for node in neighbours:
            response = requests.get(f'http://{node}/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # Check if the length is longer and the chain is valid
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        # Replace our chain if we discovered a new, valid chain longer
        if new_chain:
            self.chain = new_chain
            return True

        return False

    def new_block(self, proof, previous_hash):
        """
        Create a new Block in the Blockchain

        :param proof: The proof given by the Proof of Work algorithm
        :param previous_hash: Hash of previous Block
        :return: New Block
        """

        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }

        # Reset the current list of transactions
        self.current_transactions = []

        self.chain.append(block)
        return block

    def new_transaction(self, sender, recipient, amount):
        """
        Creates a new transaction to go into the next mined Block

        :param sender: Address of the Sender
        :param recipient: Address of the Recipient
        :param amount: Amount
        :return: The index of the Block that will hold this transaction
        """
        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })

        return self.last_block['index'] + 1

    @property
    def last_block(self):
        return self.chain[-1]

    @staticmethod
    def hash(block):
        """
        Creates a SHA-256 hash of a Block

        :param block: Block
        """

        # Ordered dictionary to avoid inconsistent hashes
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def proof_of_work(self, last_block):
        """
        Simple Proof of Work Algorithm:

         - Find a number p' such that hash(pp') contains leading 4 zeroes
         - Where p is the previous proof, and p' is the new proof

        :param last_block: <dict> last Block
        :return: <int>
        """

        last_proof = last_block['proof']
        last_hash = self.hash(last_block)

        proof = 0
        while self.valid_proof(last_proof, proof, last_hash) is False:
            proof += 1

        return proof

    @staticmethod
    def valid_proof(last_proof, proof, last_hash):
        """
        Validates the Proof

        :param last_proof: <int> Previous Proof
        :param proof: <int> Current Proof
        :param last_hash: <str> The hash of the Previous Block
        :return: <bool> True if correct, False if not.

        """

        guess = f'{last_proof}{proof}{last_hash}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"


# Instantiate the Node
app = Flask(__name__)

# Generate a globally unique address for this node
node_identifier = str(uuid4()).replace('-', '')

# Instantiate the Blockchain
blockchain = Blockchain()


@app.route('/')
def homepage():
    return render_template('home.html')


@app.route('/home', methods=['GET', 'POST'])
def home():
    # Create a local list to store dictionary of transactions
    tlist = []
    if request.method == 'POST':
        data = pd.read_csv('energydemand.csv')  # Reading the CSV file
        enerquire = float(request.form['UnitsRequired'])
        buyername = request.form['FullName']
        minimum = data['PPU'].idxmin()  # Row with Minimum Price per Unit
        if enerquire > data['Units'].sum():
            print('Market limit exceeded.')
        else:
            while data.iloc[minimum]['Units'] < enerquire:
                a = {"sender": buyername}
                a.update({"recipient": data.iloc[minimum]['Name']})
                a.update({"amount": data.iloc[minimum]['Price']})
                tlist.append(a)
                enerquire -= data.iloc[minimum]['Units']
                data = data.drop(data.index[minimum]).reset_index(drop=True)
                minimum = data['PPU'].idxmin()
            if data.iloc[minimum]['Units'] == enerquire:
                a = {"sender": buyername}
                a.update({"recipient": data.iloc[minimum]['Name']})
                a.update({"amount": data.iloc[minimum]['Price']})
                tlist.append(a)
                data = data.drop(data.index[minimum]).reset_index(drop=True)
            else:
                a = {"sender": buyername}
                a.update({"recipient": data.iloc[minimum]['Name']})
                a.update({"amount": (enerquire * data.iloc[minimum]['PPU'])})
                tlist.append(a)
                data.loc[minimum, 'Units'] -= enerquire
                data.loc[minimum, 'Price'] -= \
                    enerquire * data.loc[minimum, 'PPU']
            data.to_csv(
                'energydemand.csv', sep=',', encoding='utf-8', index=False)
        for transaction in tlist:
            blockchain.new_transaction(
                transaction['sender'],
                transaction['recipient'], transaction['amount'])
        return render_template('home.html')
    else:
        return render_template('home.html')


@app.route('/buyenergy')
def buyenergy():
    return render_template('buyenergy.html')


@app.route('/sellenergy')
def sellenergy():
    return render_template('sellenergy.html', title='Sell')


@app.route('/table', methods=['GET', 'POST'])
def table():
    '''
    Acquire the values of the seller from the HTTP Form
    Add The Current DateTime
    Add it to the table for convenience of the general participant
    '''
    if request.method == 'POST':
        name = request.form['FullName']
        units = float(request.form['AvailableUnits'])
        ppu = float(request.form['PricePerUnit'])
        price = ppu * units
        now = datetime.now()
        ts = now.strftime("%d-%m-%y %H:%M")
        data = pd.read_csv('energydemand.csv')
        df1 = pd.DataFrame(data=[[name, price, units, ppu, ts]], columns=[
                           "Name", "Price", "Units", "PPU", "Time"])
        df1.to_csv('energydemand.csv', mode='a', header=False, index=False)
        data = pd.concat([data, df1], axis=0)
        data.index = range(len(data.index))
        data.index += 1
        return render_template(
            'table.html', data=data.to_html(), title='Table')
    else:
        data = pd.read_csv('energydemand.csv')
        data.index = range(len(data.index))
        data.index += 1
        return render_template(
            'table.html', data=data.to_html(), title='Table')


@app.route('/transact')
def transact():
    # List of transactions that have been mined/approved
    data = pd.read_csv('transacttable.csv')
    data.index = range(len(data.index))
    data.index += 1
    return render_template(
        'transact.html', data=data.to_html(), title='Transactions')


@app.route('/mine', methods=['GET'])
def mine():
    # We run the proof of work algorithm to get the next proof...
    last_block = blockchain.last_block
    proof = blockchain.proof_of_work(last_block)
    # We must receive a reward for finding the proof.
    # The sender is "0" to signify that this node has mined a new coin.
    blockchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1,
    )

    # Forge the new Block by adding it to the chain
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash'],
    }
    trans = block['transactions']
    for i in trans[:-1]:
        sender = i['sender']
        recipient = i['recipient']
        amount = i['amount']
        now = datetime.now()
        ts = now.strftime("%d-%m-%y %H:%M")
        data = pd.read_csv('transacttable.csv')
        df1 = pd.DataFrame(data=[[sender, recipient, amount, ts]], columns=[
            "Sender", "Recipient", "Amount", "Time"])
        df1.to_csv('transacttable.csv', mode='a', header=False, index=False)
        data = pd.concat([data, df1], axis=0)
        data.index = range(len(data.index))
        data.index += 1

    return jsonify(response), 200


@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200


@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()

    nodes = values.get('nodes')
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(blockchain.nodes),
    }
    return jsonify(response), 201


@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }

    return jsonify(response), 200


if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument(
        '-p', '--port', default=5000, type=int, help='port to listen on')
    args = parser.parse_args()
    port = args.port

    app.run(host='0.0.0.0', port=port)
